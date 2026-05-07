"""regulated-rag: production-pattern RAG for regulated domains.

v0.1 corpus: FDCPA + California EWA. Public API exports below are the
stable surface; everything else is internal.
"""

from .chunker import (
    Chunk,
    FDCPA_SECTIONS,
    chunk_full_fdcpa,
    iter_full_fdcpa,
    parse_section,
)
from .embedder import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EmbeddingResult,
    compose_embedding_input,
    embed_chunks,
    embed_query,
)

__all__ = [
    "Chunk",
    "FDCPA_SECTIONS",
    "chunk_full_fdcpa",
    "iter_full_fdcpa",
    "parse_section",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "EmbeddingResult",
    "compose_embedding_input",
    "embed_chunks",
    "embed_query",
]
