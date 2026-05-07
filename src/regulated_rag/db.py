"""
Database helpers for the regulated-rag chunks table.

Design notes
------------
- psycopg v3 (NOT psycopg2). Connection strings via DATABASE_URL env var by
  default; falls back to SUPABASE_DB_URL if that's the convention in your env.
- pgvector.psycopg.register_vector() is called per-connection to enable
  native conversion between Python lists and Postgres `vector` type. Without
  this, you'd have to format vectors as `[0.1, 0.2, ...]` strings manually.
- Two-phase ingest contract:
    Phase 1: insert chunks with embedding=NULL (rows visible, but not yet
             retrievable). Survives crashes mid-embed.
    Phase 2: SELECT WHERE embedding IS NULL AND source=..., embed, UPDATE.
  This is why schema.sql made `embedding` nullable — it's deliberate.
- All metadata-only fields go into the JSONB `metadata` column. The top-level
  columns (`source`, `section_ref`, `chunk_text`, `embedding`) are the hot
  query path; everything else can stay in JSONB and be queried via the GIN
  index when needed.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector

from .chunker import Chunk
from .embedder import EmbeddingResult

logger = logging.getLogger(__name__)


def _connection_string() -> str:
    """Resolve the Postgres DSN from env. DATABASE_URL preferred."""
    for var in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL"):
        val = os.getenv(var)
        if val:
            return val
    raise RuntimeError(
        "No Postgres connection string found. Set DATABASE_URL "
        "(or SUPABASE_DB_URL / POSTGRES_URL) in your .env file. "
        "The smoke test from hour 1-2 used the same env var; if that "
        "passed, this should be set."
    )


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """
    Open a Postgres connection with pgvector type registration. Use as:

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    dsn = _connection_string()
    conn = psycopg.connect(dsn)
    try:
        register_vector(conn)
        yield conn
    finally:
        conn.close()


def count_by_source(conn: psycopg.Connection, source: str) -> int:
    """How many rows exist for this source label."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM chunks WHERE source = %s", (source,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def delete_by_source(conn: psycopg.Connection, source: str) -> int:
    """
    DELETE all rows for a source. Returns row count deleted.
    The caller is responsible for committing the transaction.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE source = %s", (source,))
        return cur.rowcount


def insert_chunks_without_embeddings(
    conn: psycopg.Connection,
    chunks: list[Chunk],
) -> list[int]:
    """
    Phase 1 insert: writes chunks with embedding=NULL. Returns the auto-
    generated ids in input order so phase 2 can target them by id.

    Inserted via executemany for batching; ids returned via RETURNING id.
    """
    if not chunks:
        return []

    sql = """
        INSERT INTO chunks (source, section_ref, chunk_text, metadata, embedding)
        VALUES (%s, %s, %s, %s::jsonb, NULL)
        RETURNING id
    """
    ids: list[int] = []
    with conn.cursor() as cur:
        # psycopg v3 supports executemany but doesn't surface RETURNING for
        # batch inserts. We loop — for ~85 FDCPA chunks the round-trip cost
        # is ~85 ms total, well within budget.
        for chunk in chunks:
            cur.execute(sql, (
                chunk.source,
                chunk.section_ref,
                chunk.chunk_text,
                json.dumps(chunk.metadata),
            ))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(
                    f"INSERT for {chunk.section_ref} did not return an id."
                )
            ids.append(int(row[0]))
    return ids


def update_chunk_embeddings(
    conn: psycopg.Connection,
    pairs: list[tuple[int, list[float]]],
) -> int:
    """
    Phase 2 update: SET embedding for each (id, vector) pair.

    The `%s::vector` cast is required because psycopg adapts a Python list
    to `double precision[]` by default. Same defensive fix used in cosine_search.

    Returns rows updated. Caller commits.
    """
    if not pairs:
        return 0
    sql = "UPDATE chunks SET embedding = %s::vector WHERE id = %s"
    updated = 0
    with conn.cursor() as cur:
        for chunk_id, embedding in pairs:
            cur.execute(sql, (embedding, chunk_id))
            updated += cur.rowcount
    return updated


def fetch_unembedded_chunks(
    conn: psycopg.Connection, source: str,
) -> list[tuple[int, str, dict]]:
    """
    Find chunks with embedding IS NULL for a given source. Returns
    (id, chunk_text, metadata) triples — caller composes the embedding
    input via embedder.compose_embedding_input.
    """
    sql = """
        SELECT id, section_ref, chunk_text, metadata
        FROM chunks
        WHERE source = %s AND embedding IS NULL
        ORDER BY id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source,))
        return [
            (int(row[0]), row[2], dict(row[3]) if row[3] else {})
            # row[1] (section_ref) is implicitly available via metadata too;
            # we drop it from the return tuple since the embedder only needs
            # chunk_text + metadata to compose the prefix.
            for row in cur.fetchall()
        ]


def cosine_search(
    conn: psycopg.Connection,
    query_embedding: list[float],
    source: str,
    limit: int = 5,
) -> list[dict]:
    """
    Cosine-similarity search against `chunks.embedding`. Returns top-`limit`
    rows ordered by similarity descending. Pgvector's `<=>` operator returns
    cosine *distance*, so similarity = 1 - distance.

    The `%s::vector` casts are required because psycopg adapts a Python list
    to `double precision[]` by default; pgvector's `<=>` operator only
    accepts `vector` on both sides. The cast is the defensive fix that works
    regardless of how pgvector adapter registration is configured.
    """
    sql = """
        SELECT
            id,
            section_ref,
            chunk_text,
            metadata,
            1 - (embedding <=> %s::vector) AS similarity
        FROM chunks
        WHERE source = %s AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (query_embedding, source, query_embedding, limit))
        rows = cur.fetchall()
    return [
        {
            "id": int(r[0]),
            "section_ref": r[1],
            "chunk_text": r[2],
            "metadata": dict(r[3]) if r[3] else {},
            "similarity": float(r[4]),
        }
        for r in rows
    ]
    
def get_all_chunks(
    conn: psycopg.Connection,
    source: str,
) -> list[dict]:
    """
    Fetch every embedded chunk for a source. Used by BM25 to build the
    in-memory index.

    Filtered to `embedding IS NOT NULL` so half-ingested chunks (the
    insert-then-embed contract from hour 3) don't poison the index when
    ingest is interrupted mid-run.
    """
    sql = """
        SELECT id, source, section_ref, chunk_text, metadata
        FROM chunks
        WHERE source = %s AND embedding IS NOT NULL
        ORDER BY id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source,))
        rows = cur.fetchall()
    return [
        {
            "id": int(r[0]),
            "source": r[1],
            "section_ref": r[2],
            "chunk_text": r[3],
            "metadata": dict(r[4]) if r[4] else {},
        }
        for r in rows
    ]


def get_chunks_by_ids(
    conn: psycopg.Connection,
    chunk_ids: list[int],
) -> list[dict]:
    """
    Fetch chunks by id, preserving input order. Used by the retrieval
    pipeline to hydrate top-N RRF results before rerank.

    Order preservation matters: RRF gives us a ranked id list; the
    reranker returns indices that must map back to the right chunks.
    """
    if not chunk_ids:
        return []
    sql = """
        SELECT id, source, section_ref, chunk_text, metadata
        FROM chunks
        WHERE id = ANY(%s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (chunk_ids,))
        rows = cur.fetchall()
    rows_by_id = {
        int(r[0]): {
            "id": int(r[0]),
            "source": r[1],
            "section_ref": r[2],
            "chunk_text": r[3],
            "metadata": dict(r[4]) if r[4] else {},
        }
        for r in rows
    }
    return [rows_by_id[cid] for cid in chunk_ids if cid in rows_by_id]
