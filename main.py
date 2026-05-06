import os
import time
import json
import cohere
import voyageai
import anthropic
from rank_bm25 import BM25Okapi
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
co = cohere.Client(api_key=os.environ["COHERE_API_KEY"])

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


# ── Hybrid search helpers ──────────────────────────────────────────

def semantic_search(query_vector: list[float], top_k: int = 20) -> list[dict]:
    """Vector similarity search via pgvector."""
    response = supabase.rpc("match_chunks", {
        "query_embedding": query_vector,
        "match_user_id": USER_ID,
        "match_count": top_k,
        "match_threshold": 0.1
    }).execute()
    return response.data or []


def keyword_search(query: str, all_chunks: list[dict], top_k: int = 20) -> list[dict]:
    """BM25 keyword search over fetched chunks."""
    if not all_chunks:
        return []

    tokenized = [c["content"].lower().split() for c in all_chunks]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())

    ranked = sorted(
        enumerate(scores),
        key=lambda x: x[1],
        reverse=True
    )[:top_k]

    results = []
    for idx, score in ranked:
        if score > 0:
            chunk = all_chunks[idx].copy()
            chunk["bm25_score"] = score
            results.append(chunk)
    return results


def reciprocal_rank_fusion(
    semantic: list[dict],
    keyword: list[dict],
    k: int = 60
) -> list[dict]:
    """Merge semantic and keyword results using RRF."""
    scores = {}
    chunk_map = {}

    for rank, chunk in enumerate(semantic):
        cid = chunk["id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        chunk_map[cid] = chunk

    for rank, chunk in enumerate(keyword):
        cid = chunk["id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        chunk_map[cid] = chunk

    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [chunk_map[cid] for cid, _ in sorted_ids]


def rerank(query: str, chunks: list[dict], top_n: int = 5) -> list[dict]:
    """Rerank candidates using Cohere reranker."""
    if not chunks:
        return []

    docs = [c["content"] for c in chunks]
    response = co.rerank(
        model="rerank-english-v3.0",
        query=query,
        documents=docs,
        top_n=min(top_n, len(docs))
    )

    reranked = []
    for r in response.results:
        chunk = chunks[r.index].copy()
        chunk["rerank_score"] = r.relevance_score
        reranked.append(chunk)

    return reranked


def hybrid_search_pipeline(question: str, top_k: int = 5) -> list[dict]:
    """Full pipeline: embed → semantic → keyword → RRF → rerank."""

    # 1. Embed the question
    time.sleep(20)
    result = voyage.embed([question], model="voyage-3", input_type="query")
    query_vector = result.embeddings[0]

    # 2. Semantic search — get top 20
    semantic_results = semantic_search(query_vector, top_k=20)
    print(f"   Semantic: {len(semantic_results)} results")

    if not semantic_results:
        return []

    # 3. Keyword search — BM25 over the same chunks
    keyword_results = keyword_search(question, semantic_results, top_k=20)
    print(f"   Keyword: {len(keyword_results)} results")

    # 4. RRF merge
    fused = reciprocal_rank_fusion(semantic_results, keyword_results)
    print(f"   After RRF: {len(fused)} results")

    # 5. Rerank top candidates
    reranked = rerank(question, fused[:20], top_n=top_k)
    print(f"   After reranking: {len(reranked)} results")

    return reranked


# ── Routes ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "pipeline": "hybrid_search + reranking"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files supported")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        doc_result = supabase.table("documents").insert({
            "name": file.filename,
            "size_bytes": len(content),
            "user_id": USER_ID
        }).execute()
        doc_id = doc_result.data[0]["id"]

        pages = extract_text(tmp_path)
        chunks = chunk_pages(pages)

        if not chunks:
            raise HTTPException(
                status_code=400, detail="No text could be extracted from PDF")

        texts = [c["content"] for c in chunks]
        embeddings = embed_texts(texts)

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

    print(f"\n🔍 Question: {request.question}")

    chunks = hybrid_search_pipeline(request.question)

    if not chunks:
        return {
            "answer": "I don't have that information in the provided documents.",
            "sources": [],
            "pipeline": "hybrid + rerank"
        }

    # Confidence check
    top_score = chunks[0].get("rerank_score", 0)
    if top_score < 0.1:
        return {
            "answer": "I couldn't find relevant information to answer this question confidently.",
            "sources": [],
            "confidence": round(top_score, 3),
            "pipeline": "hybrid + rerank"
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
        "sources": [{
            "page": c["page_number"],
            "rerank_score": round(c.get("rerank_score", 0), 3)
        } for c in chunks],
        "confidence": round(top_score, 3),
        "pipeline": "hybrid + rerank"
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
