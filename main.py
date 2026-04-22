import os
import time
import voyageai
import anthropic
from supabase import create_client
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import PyPDF2
import tempfile

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
client = anthropic.Anthropic()

USER_ID = "satya_123"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

SYSTEM_PROMPT = """You are a document assistant. Answer questions using ONLY the provided document excerpts.
If the answer is not in the excerpts, say "I don't have that information in the provided documents."
Always cite which excerpt you used by mentioning the page number."""


# ── Ingestion helpers ──────────────────────────────────────────────

def extract_text(pdf_path: str) -> list[dict]:
    pages = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append({"page_number": i + 1, "text": text.strip()})
    return pages


def chunk_pages(pages: list[dict]) -> list[dict]:
    chunks = []
    for page in pages:
        words = page["text"].split()
        start = 0
        while start < len(words):
            chunk = " ".join(words[start:start + CHUNK_SIZE])
            if len(chunk.strip()) > 50:
                chunks.append(
                    {"content": chunk, "page_number": page["page_number"]})
            start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    all_embeddings = []
    for i in range(0, len(texts), 128):
        batch = texts[i:i + 128]
        result = voyage.embed(batch, model="voyage-3", input_type="document")
        all_embeddings.extend(result.embeddings)
        if i + 128 < len(texts):
            time.sleep(20)
    return all_embeddings


# ── Routes ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files supported")

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Store document record
        doc_result = supabase.table("documents").insert({
            "name": file.filename,
            "size_bytes": len(content),
            "user_id": USER_ID
        }).execute()
        doc_id = doc_result.data[0]["id"]

        # Extract + chunk
        pages = extract_text(tmp_path)
        chunks = chunk_pages(pages)

        if not chunks:
            raise HTTPException(
                status_code=400, detail="No text could be extracted from PDF")

        # Embed
        texts = [c["content"] for c in chunks]
        embeddings = embed_texts(texts)

        # Store chunks
        rows = [{
            "document_id": doc_id,
            "user_id": USER_ID,
            "content": chunks[i]["content"],
            "embedding": embeddings[i],
            "page_number": chunks[i]["page_number"],
            "chunk_index": i
        } for i in range(len(chunks))]

        for i in range(0, len(rows), 50):
            supabase.table("chunks").insert(rows[i:i + 50]).execute()

        return {
            "document_id": doc_id,
            "filename": file.filename,
            "pages": len(pages),
            "chunks": len(chunks)
        }

    finally:
        os.unlink(tmp_path)


class QuestionRequest(BaseModel):
    question: str
    document_id: str | None = None


@app.post("/ask")
async def ask_question(request: QuestionRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Embed the question
    time.sleep(20)
    result = voyage.embed([request.question],
                          model="voyage-3", input_type="query")
    query_vector = result.embeddings[0]

    # Search chunks
    response = supabase.rpc("match_chunks", {
        "query_embedding": query_vector,
        "match_user_id": USER_ID,
        "match_count": 5,
        "match_threshold": 0.3
    }).execute()

    chunks = response.data

    if not chunks:
        return {
            "answer": "I don't have that information in the provided documents.",
            "sources": []
        }

    # Build context
    context = "\n\n".join([
        f"[Excerpt {i+1} — Page {c['page_number']}]\n{c['content']}"
        for i, c in enumerate(chunks)
    ])

    # Ask Claude
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{
            "role": "user",
            "content": f"Here are the relevant excerpts:\n\n{context}\n\nQuestion: {request.question}"
        }]
    )

    return {
        "answer": message.content[0].text,
        "sources": [{"page": c["page_number"], "similarity": round(c["similarity"], 3)} for c in chunks]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
