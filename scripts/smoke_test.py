"""Smoke test: verify all four connections work before we proceed.

Tests:
1. Supabase Postgres connection + pgvector extension
2. Voyage AI API (one-token embedding)
3. Cohere API (rerank one trivial pair)
4. Anthropic API (one-token completion)

Run: python scripts/smoke_test.py
"""

import os
import sys
from pathlib import Path

# Add src to path for imports if needed (we're not importing from src here, but for future)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()


def test_supabase():
    """Verify Postgres connection and pgvector extension."""
    import psycopg

    db_url = os.environ["DATABASE_URL"]
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Verify pgvector extension is installed
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            result = cur.fetchone()
            assert result is not None, "pgvector extension not installed"

            # Verify chunks table exists
            cur.execute(
                "SELECT to_regclass('public.chunks');"
            )
            result = cur.fetchone()
            assert result[0] == "chunks", "chunks table not found"

            # Verify chunks is empty (sanity check)
            cur.execute("SELECT COUNT(*) FROM chunks;")
            count = cur.fetchone()[0]
            print(f"  → Postgres: connected, pgvector enabled, chunks table found ({count} rows)")


def test_voyage():
    """Verify Voyage AI embedding endpoint."""
    import voyageai

    client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    result = client.embed(
        ["test"], model="voyage-3-large", input_type="document"
    )
    assert len(result.embeddings) == 1
    assert len(result.embeddings[0]) == 1024
    print(f"  → Voyage: embedded 'test' → 1024-dim vector ✓")


def test_cohere():
    """Verify Cohere rerank endpoint."""
    import cohere

    client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    result = client.rerank(
        model="rerank-v3.5",
        query="what is debt collection",
        documents=["debt collection rules", "weather forecast"],
        top_n=2,
    )
    assert len(result.results) == 2
    print(f"  → Cohere: reranked 2 docs, top score {result.results[0].relevance_score:.3f} ✓")


def test_anthropic():
    """Verify Anthropic generation endpoint."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    result = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": "Reply with just 'ok'"}],
    )
    assert result.content[0].text
    print(f"  → Anthropic: generated response ✓")


def main():
    print("Running smoke tests...\n")

    tests = [
        ("Supabase + pgvector", test_supabase),
        ("Voyage AI", test_voyage),
        ("Cohere", test_cohere),
        ("Anthropic", test_anthropic),
    ]

    failures = []
    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            print(f"  ✗ {name} FAILED: {e}")
            failures.append((name, e))

    print()
    if failures:
        print(f"❌ {len(failures)} of {len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"✅ All {len(tests)} smoke tests passed")


if __name__ == "__main__":
    main()