-- regulated-rag schema
-- v0.1 — single chunks table for FDCPA + California EWA
-- Manually built in Supabase Table Editor; this file is the canonical version.

-- Required extension: pgvector for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Main corpus table
CREATE TABLE IF NOT EXISTS chunks (
    id              bigserial PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    source          text NOT NULL,
    section_ref     text NOT NULL,
    chunk_text      text NOT NULL,
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(1024)
);

-- HNSW index for vector cosine similarity
-- m=16, ef_construction=64 are pgvector defaults; sufficient for v0.1 scale (~2,500 chunks)
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Btree index for fast corpus filtering (source = 'fdcpa' / 'california_ewa')
CREATE INDEX IF NOT EXISTS chunks_source_idx ON chunks (source);

-- GIN index for jsonb metadata queries
CREATE INDEX IF NOT EXISTS chunks_metadata_idx ON chunks USING gin (metadata);

-- Notes:
-- 1. RLS deliberately disabled. The Python ingestion/retrieval code uses the
--    Supabase service-role key, which bypasses RLS. There is no per-user data
--    isolation in v0.1 — this is a single shared corpus.
-- 2. The `embedding` column is nullable to allow chunks to be ingested in two
--    phases: chunk + insert first, embed + update later. This makes ingestion
--    resumable on API failure.
-- 3. Voyage `voyage-3-large` produces 1024-dimensional vectors. If the embedder
--    changes, this dimension MUST change in lockstep — pgvector will reject
--    inserts of differently-dimensioned vectors.