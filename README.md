# Smart Document Analyzer

An AI-powered document Q&A system with production-quality retrieval. Upload PDFs, ask questions in plain English, and get accurate answers grounded in your documents — not AI hallucinations.

**🔗 Frontend:** https://ai-document-analyzer-ten.vercel.app

**⚙️ Backend:** https://ai-document-analyzer-production-20f8.up.railway.app

![Claude API](https://img.shields.io/badge/Built%20with-Claude%20API-blue) ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-green) ![Next.js](https://img.shields.io/badge/Frontend-Next.js-black) ![Supabase](https://img.shields.io/badge/Vector%20DB-pgvector-orange)

---

## Features

- **PDF upload** — drag and drop or click to upload
- **Multi-document support** — manage multiple PDFs, switch between them, delete individually
- **Hybrid search** — semantic vector search + BM25 keyword search combined via Reciprocal Rank Fusion
- **Cohere reranking** — second-pass relevance scoring for production-quality retrieval
- **Confidence scoring** — refuses to answer when retrieval confidence is too low
- **Source citations** — every answer shows page number + relevance percentage
- **Prompt caching** — 90% cost reduction on repeated system prompt tokens

---

## Tech Stack

| Layer           | Technology                            |
| --------------- | ------------------------------------- |
| Frontend        | Next.js 16, TypeScript, Tailwind CSS  |
| Backend         | Python, FastAPI, Uvicorn              |
| AI — Generation | Claude API (claude-sonnet-4-6)        |
| AI — Embeddings | Voyage AI (voyage-3, 1024 dimensions) |
| AI — Reranking  | Cohere (rerank-english-v3.0)          |
| Vector Database | Supabase pgvector                     |
| Keyword Search  | BM25 (rank_bm25)                      |
| Deployment      | Vercel (frontend) + Railway (backend) |

---

## How It Works

### Ingestion pipeline (runs once per document)

```
PDF upload → extract text → chunk (400 tokens, 50 overlap)
→ Voyage AI embedding → store in Supabase pgvector
```

### Retrieval pipeline (runs on every question)

```
Question → embed (Voyage AI)
→ Semantic search (pgvector cosine similarity, top 20)
→ BM25 keyword search (rank_bm25, top 20)
→ Reciprocal Rank Fusion (RRF merge)
→ Cohere reranking (top 5 from merged 20)
→ Confidence check (refuse if score < 0.1)
→ Claude answers with citation constraint
```

### Why hybrid search + reranking?

- **Semantic only** fails on exact terms — "refund policy" retrieves "returns policy" first
- **Keyword only** fails on conceptual queries — misses paraphrases
- **Hybrid** handles both — correct chunk rises to top regardless of phrasing
- **Reranking** reads actual text to confirm relevance — eliminates false positives

---

## Project Structure

```
document-analyzer/
├── main.py              # FastAPI backend
│   ├── POST /upload     # PDF ingestion pipeline
│   ├── POST /ask        # Hybrid search + Claude Q&A
│   ├── GET  /documents  # List all documents
│   └── DELETE /documents/{id}  # Delete document + chunks
├── ingest.py            # Standalone ingestion script
├── query.py             # Standalone query script
├── requirements.txt
├── nixpacks.toml        # Railway deployment config
├── .env                 # API keys (not committed)
└── ui/
    ├── app/
    │   └── page.tsx     # Multi-document UI
    └── vercel.json
```

---

## Running Locally

**Backend**

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Add to .env:
# ANTHROPIC_API_KEY=...
# VOYAGE_API_KEY=...
# SUPABASE_URL=...
# SUPABASE_KEY=...
# COHERE_API_KEY=...

uvicorn main:app --reload
# Runs on http://localhost:8000
```

**Frontend**

```bash
cd ui
npm install
npm run dev
# Runs on http://localhost:3000
```

---

## Database Setup (Supabase)

Run this SQL in your Supabase SQL Editor:

```sql
create extension if not exists vector;

create table documents (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  size_bytes integer,
  user_id text not null,
  created_at timestamp with time zone default now()
);

create table chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid references documents(id) on delete cascade,
  user_id text not null,
  content text not null,
  embedding vector(1024),
  page_number integer,
  chunk_index integer,
  created_at timestamp with time zone default now()
);

create index on chunks using ivfflat (embedding vector_cosine_ops)
with (lists = 100);

create or replace function match_chunks(
  query_embedding vector(1024),
  match_user_id text,
  match_count int default 5,
  match_threshold float default 0.5
)
returns table (
  id uuid, content text, page_number integer,
  document_id uuid, similarity float
)
language sql stable as $$
  select chunks.id, chunks.content, chunks.page_number,
         chunks.document_id,
         1 - (chunks.embedding <=> query_embedding) as similarity
  from chunks
  where chunks.user_id = match_user_id
    and 1 - (chunks.embedding <=> query_embedding) > match_threshold
  order by chunks.embedding <=> query_embedding
  limit match_count;
$$;
```

---

## API Reference

### `POST /upload`

Upload and ingest a PDF document.

**Request:** `multipart/form-data` with `file` field

**Response:**

```json
{
  "document_id": "uuid",
  "filename": "report.pdf",
  "pages": 12,
  "chunks": 47
}
```

---

### `POST /ask`

Ask a question against a document using hybrid search + reranking.

**Request:**

```json
{
  "question": "What were the Q3 revenue figures?",
  "document_id": "uuid"
}
```

**Response:**

```json
{
  "answer": "Based on Page 4, Q3 revenue was $4.2 billion...",
  "sources": [{ "page": 4, "rerank_score": 0.97 }],
  "confidence": 0.97,
  "pipeline": "hybrid + rerank"
}
```

---

### `GET /documents`

List all uploaded documents.

### `DELETE /documents/{id}`

Delete a document and all its chunks (cascades automatically).

---

## Deployment

**Backend → Railway**

- Set env vars: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `COHERE_API_KEY`
- `nixpacks.toml` handles Python start command

**Frontend → Vercel**

- Root Directory: `ui`
- Env var: `NEXT_PUBLIC_API_URL` = Railway backend URL (not Sensitive)

---

## Built as part of a 6-month AI Engineering curriculum

This is the Month 2 portfolio project — a production RAG application with hybrid search and reranking.

Follow the journey: [@codingwithsatya](https://github.com/codingwithsatya)
