import os
import uuid
import voyageai
from anthropic import Anthropic
from supabase import create_client
from dotenv import load_dotenv
import PyPDF2

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
client = Anthropic()

CHUNK_SIZE = 400    # tokens approx (we'll use words as proxy)
CHUNK_OVERLAP = 50  # words overlap between chunks
USER_ID = "satya_123"  # hardcoded for now, will come from auth in Month 4


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """Extract text page by page from a PDF."""
    pages = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append({
                    "page_number": page_num + 1,
                    "text": text.strip()
                })
    return pages


def chunk_text(text: str, page_number: int) -> list[dict]:
    """Split text into overlapping chunks by word count."""
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + CHUNK_SIZE
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)

        if len(chunk_text.strip()) > 50:  # skip tiny chunks
            chunks.append({
                "content": chunk_text,
                "page_number": page_number
            })

        start += CHUNK_SIZE - CHUNK_OVERLAP
        if start >= len(words):
            break

    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Embed all chunks using Voyage AI."""
    texts = [c["content"] for c in chunks]

    # Voyage AI supports batches of up to 128
    embeddings = []
    batch_size = 128
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        result = voyage.embed(batch, model="voyage-3", input_type="document")
        embeddings.extend(result.embeddings)

    for i, chunk in enumerate(chunks):
        chunk["embedding"] = embeddings[i]

    return chunks


def ingest_pdf(pdf_path: str) -> str:
    """Full ingestion pipeline: PDF → chunks → embeddings → Supabase."""
    filename = os.path.basename(pdf_path)
    file_size = os.path.getsize(pdf_path)

    print(f"📄 Ingesting: {filename}")

    # 1. Store document record
    doc_result = supabase.table("documents").insert({
        "name": filename,
        "size_bytes": file_size,
        "user_id": USER_ID
    }).execute()

    doc_id = doc_result.data[0]["id"]
    print(f"   ✓ Document record created: {doc_id}")

    # 2. Extract text from PDF
    pages = extract_text_from_pdf(pdf_path)
    print(f"   ✓ Extracted {len(pages)} pages")

    # 3. Chunk all pages
    all_chunks = []
    for page in pages:
        page_chunks = chunk_text(page["text"], page["page_number"])
        all_chunks.extend(page_chunks)
    print(f"   ✓ Created {len(all_chunks)} chunks")

    # 4. Embed all chunks
    all_chunks = embed_chunks(all_chunks)
    print(f"   ✓ Embedded {len(all_chunks)} chunks")

    # 5. Store chunks in Supabase
    rows = []
    for i, chunk in enumerate(all_chunks):
        rows.append({
            "document_id": doc_id,
            "user_id": USER_ID,
            "content": chunk["content"],
            "embedding": chunk["embedding"],
            "page_number": chunk["page_number"],
            "chunk_index": i
        })

    # Insert in batches of 50
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        supabase.table("chunks").insert(batch).execute()

    print(f"   ✓ Stored {len(rows)} chunks in Supabase")
    print(f"   🎉 Done! Document ID: {doc_id}")
    return doc_id


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ingest.py path/to/document.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    ingest_pdf(pdf_path)
