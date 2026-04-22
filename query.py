import os
import voyageai
import anthropic
from supabase import create_client
from dotenv import load_dotenv
import time

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
client = anthropic.Anthropic()

USER_ID = "satya_123"

SYSTEM_PROMPT = """You are a document assistant. Answer questions using ONLY the provided document excerpts.
If the answer is not in the excerpts, say "I don't have that information in the provided documents."
Always cite which excerpt you used by mentioning the page number."""


def retrieve_chunks(question: str, top_k: int = 5) -> list[dict]:
    """Embed the question and find the most similar chunks."""
    time.sleep(20)  # simulate latency
    result = voyage.embed([question], model="voyage-3", input_type="query")
    query_vector = result.embeddings[0]

    response = supabase.rpc("match_chunks", {
        "query_embedding": query_vector,
        "match_user_id": USER_ID,
        "match_count": top_k,
        "match_threshold": 0.3
    }).execute()

    return response.data


def build_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a readable context block."""
    if not chunks:
        return "No relevant excerpts found."

    context_parts = []
    for i, chunk in enumerate(chunks):
        context_parts.append(
            f"[Excerpt {i+1} — Page {chunk['page_number']}]\n{chunk['content']}"
        )
    return "\n\n".join(context_parts)


def answer_question(question: str) -> dict:
    """Full RAG pipeline: retrieve chunks → build prompt → Claude answers."""
    print(f"\n🔍 Question: {question}")

    # 1. Retrieve relevant chunks
    chunks = retrieve_chunks(question)
    print(f"   ✓ Retrieved {len(chunks)} chunks")

    if not chunks:
        return {
            "answer": "I don't have that information in the provided documents.",
            "chunks_used": 0,
            "chunks": []
        }

    # 2. Build context from chunks
    context = build_context(chunks)

    # 3. Send to Claude
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
            "content": f"""Here are the relevant excerpts from the document:

{context}

Question: {question}"""
        }]
    )

    answer = message.content[0].text
    print(f"   ✓ Answer generated ({message.usage.output_tokens} tokens)")

    return {
        "answer": answer,
        "chunks_used": len(chunks),
        "chunks": [{"page": c["page_number"], "similarity": round(c["similarity"], 3)} for c in chunks]
    }


if __name__ == "__main__":
    # Test questions against our document
    questions = questions = [
        "What is prompt caching and how much does it save?",
        "What are tokens?",
    ]

    for question in questions:
        result = answer_question(question)
        print(f"\n💬 Answer:\n{result['answer']}")
        print(f"\n📊 Chunks used: {result['chunks_used']}")
        print(f"   Sources: {result['chunks']}")
        print("\n" + "="*60)
