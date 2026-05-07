"""
Voyage embedder for regulated-rag corpus chunks.

Design notes
------------
- The embedding *input* string is not the same as the stored `chunk_text`.
  We compose a structural prefix ("FDCPA § 806 (Harassment or abuse),
  subsection (5): ...") and prepend it to chunk_text at embed time. The
  prefix is metadata-derived, so we never persist it — if the format changes,
  re-embedding regenerates the inputs without any data drift.
- The prefix is structural context, NOT Anthropic-style Contextual Retrieval
  (which uses an LLM to generate per-chunk context summaries). v0.2 will add
  Contextual Retrieval as a measured comparison; v0.1 stays at the structural
  baseline. See CONTEXT.md "What this is *not yet*" for rationale.
- Voyage `voyage-3-large` produces 1024-dim vectors. The schema is pinned to
  vector(1024); changing the embedder requires schema migration.
- We pass `input_type="document"` for ingestion. Queries use `input_type="query"`
  via embed_query().
- Voyage's Python SDK handles batching internally up to 128 inputs per call.
  For FDCPA's ~85 chunks this is a single API call. We still wrap in a manual
  retry loop because partial-failure recovery is the v0.1 ingest contract.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import voyageai

from .chunker import Chunk

logger = logging.getLogger(__name__)

# Pinned per CONTEXT.md "Architectural decisions (locked)".
# Voyage does not currently expose dated snapshot versions for voyage-3-large
# on the direct API. The reproducibility commitment is satisfied by (a) this
# string pin and (b) the ingest log capturing model name + ingest timestamp
# in CORPUS-NOTES.md per ingest run.
EMBEDDING_MODEL = "voyage-3-large"
EMBEDDING_DIMENSIONS = 1024  # MUST match schema vector() column dimension.

# Voyage's documented per-request batch limit. Empirically the SDK accepts
# larger batches but we stay below the documented ceiling.
MAX_BATCH_SIZE = 128


@dataclass
class EmbeddingResult:
    """A chunk paired with its computed embedding vector."""
    chunk: Chunk
    embedding: list[float]
    embedding_input: str   # the actual string sent to the embedder, for debugging


def compose_embedding_input(chunk: Chunk) -> str:
    """
    Build the structural-prefixed string that gets sent to the embedder.

    Pattern: "FDCPA § {section} ({title}){subsection_suffix}: {chunk_text}"

    Examples:
        FDCPA § 806 (Harassment or abuse), subsection (5): Causing a telephone...
        FDCPA § 805 (Communication in connection with debt collection), subsection (a)(1): at any unusual time...
        FDCPA § 806 (Harassment or abuse): A debt collector may not engage...   [framing clause, no subsection]
    """
    fdcpa_section = chunk.metadata["fdcpa_section"]
    section_title = chunk.metadata["section_title"]
    path = chunk.metadata.get("fdcpa_subsection_path", [])
    if path:
        subsection_suffix = ", subsection " + "".join(f"({m})" for m in path)
    else:
        subsection_suffix = ""
    return (
        f"FDCPA § {fdcpa_section} ({section_title}){subsection_suffix}: "
        f"{chunk.chunk_text}"
    )


def _get_client() -> voyageai.Client:
    """Voyage client; expects VOYAGE_API_KEY env var."""
    if not os.getenv("VOYAGE_API_KEY"):
        raise RuntimeError(
            "VOYAGE_API_KEY not set. Add it to .env. "
            "Smoke test (run from hour 1-2) requires the same key."
        )
    return voyageai.Client()


def _embed_batch_with_retry(
    client: voyageai.Client,
    texts: list[str],
    *,
    input_type: str,
    max_retries: int = 4,
    initial_backoff: float = 2.0,
) -> list[list[float]]:
    """Embed a single batch with exponential-backoff retry."""
    backoff = initial_backoff
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            result = client.embed(
                texts=texts,
                model=EMBEDDING_MODEL,
                input_type=input_type,
                truncation=True,
            )
            embeddings = result.embeddings
            if len(embeddings) != len(texts):
                raise RuntimeError(
                    f"Voyage returned {len(embeddings)} embeddings for "
                    f"{len(texts)} inputs — count mismatch."
                )
            for i, emb in enumerate(embeddings):
                if len(emb) != EMBEDDING_DIMENSIONS:
                    raise RuntimeError(
                        f"Voyage returned embedding of length {len(emb)} "
                        f"for input {i}; expected {EMBEDDING_DIMENSIONS}. "
                        f"Schema vector() dimension and model output diverged."
                    )
            return embeddings
        except Exception as exc:  # noqa: BLE001 — Voyage SDK error taxonomy is broad
            last_exc = exc
            if attempt == max_retries:
                break
            logger.warning(
                "Voyage embed failed on attempt %d/%d: %s. Retrying in %.1fs.",
                attempt, max_retries, exc, backoff,
            )
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(
        f"Voyage embed failed after {max_retries} attempts: {last_exc}"
    ) from last_exc


def embed_chunks(
    chunks: list[Chunk],
    *,
    batch_size: int = MAX_BATCH_SIZE,
    client: voyageai.Client | None = None,
) -> list[EmbeddingResult]:
    """
    Embed a list of chunks for ingestion (input_type='document').

    Returns one EmbeddingResult per input chunk, in input order. The caller
    is responsible for persisting the embeddings to the database.
    """
    if not chunks:
        return []
    cli = client or _get_client()
    inputs = [compose_embedding_input(c) for c in chunks]

    results: list[EmbeddingResult] = []
    for batch_start in range(0, len(chunks), batch_size):
        batch_end = min(batch_start + batch_size, len(chunks))
        batch_inputs = inputs[batch_start:batch_end]
        batch_chunks = chunks[batch_start:batch_end]
        logger.info(
            "Embedding chunks %d..%d of %d", batch_start, batch_end - 1, len(chunks),
        )
        embeddings = _embed_batch_with_retry(
            cli, batch_inputs, input_type="document",
        )
        for chunk, emb, inp in zip(batch_chunks, embeddings, batch_inputs):
            results.append(EmbeddingResult(
                chunk=chunk, embedding=emb, embedding_input=inp,
            ))
    return results


def embed_query(query: str, *, client: voyageai.Client | None = None) -> list[float]:
    """Embed a retrieval query (input_type='query'). Single string in, single vector out."""
    cli = client or _get_client()
    embeddings = _embed_batch_with_retry(
        cli, [query], input_type="query",
    )
    return embeddings[0]
