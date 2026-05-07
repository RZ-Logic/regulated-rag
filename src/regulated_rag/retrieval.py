"""
Hybrid retrieval pipeline: vector + BM25 -> RRF -> cross-encoder rerank -> top-K.

Where the LLM is in this module: nowhere. Every stage here is deterministic
given pinned models. The stochastic stage (generation) lives in generation.py
and is bounded by deterministic checks on both sides: this retrieval layer
on the input side, citation grounding + refusal on the output side. See
README "Where is the LLM?" table.

Refusal is a first-class output. Below the configured top-1 reranker score
threshold, we return a refusal with reason rather than passing weak retrieval
to the generator. The threshold is a deterministic check, not a prompt
instruction.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import cohere
import yaml
from rank_bm25 import BM25Okapi

from regulated_rag.db import (
    connect,
    cosine_search,
    get_all_chunks,
    get_chunks_by_ids,
)
from regulated_rag.embedder import embed_query

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


@dataclass
class RetrievedChunk:
    """A chunk with the score from every stage that touched it. The full
    audit trail travels with the chunk; the generator and citation-grounding
    check both consume this."""

    chunk_id: int
    source: str
    section_ref: str
    chunk_text: str
    metadata: dict
    vector_score: Optional[float] = None    # cosine similarity, if hit by vector
    bm25_score: Optional[float] = None      # raw BM25, if hit by BM25
    rrf_score: Optional[float] = None       # post-fusion
    rerank_score: Optional[float] = None    # final ranking signal


@dataclass
class RetrievalResult:
    """Pipeline output: either top-K chunks or a refusal with reason.
    `refused` is the deterministic check on the output side of retrieval."""

    query: str
    chunks: list[RetrievedChunk]
    refused: bool
    refusal_reason: Optional[str] = None
    refusal_message: Optional[str] = None  # user-facing copy from config
    top_rerank_score: Optional[float] = None


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _config() -> dict:
    """Retrieval params loaded once. Restart Python to pick up edits."""
    with Path("config/retrieval.yml").open() as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _models_config() -> dict:
    """Model pins loaded once. Reranker model name lives in models.yml per
    the project's pinning convention (model strings = models.yml; retrieval
    params = retrieval.yml)."""
    with Path("config/models.yml").open() as f:
        return yaml.safe_load(f)


def _rerank_model() -> str:
    """Return the pinned rerank model string from models.yml.
    Tolerant of either flat (`cohere: rerank-v3.5`) or nested
    (`cohere: {rerank: rerank-v3.5}`) shapes."""
    cfg = _models_config()
    val = cfg.get("cohere")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("rerank") or val.get("model") or "rerank-v3.5"
    return "rerank-v3.5"


# ---------------------------------------------------------------------------
# BM25 -- module-level lazy cache, keyed by source
# ---------------------------------------------------------------------------
# Cache is per-source so v0.2 (FDCPA + EWA) can hold both indexes simultaneously
# without a cold rebuild on every cross-corpus query.
# Restart the process after re-ingesting to refresh; reset_bm25_cache() for tests.

_BM25_CACHE: dict[str, tuple[BM25Okapi, list[dict]]] = {}


def _tokenize(text: str) -> list[str]:
    """Lowercase + alphanumeric split that preserves the section marker `§`
    as its own token. No stopword removal -- BM25's IDF already deweights
    common terms, and 'the'/'a' carry trivial signal relative to rare
    statutory terms; v0.1 doesn't tune what doesn't matter."""
    text = text.replace("§", " § ")
    return re.findall(r"[a-z0-9§]+", text.lower())


def _build_bm25_index(source: str) -> tuple[BM25Okapi, list[dict]]:
    """Pull the full corpus for a source, tokenize over `section_ref + chunk_text`.

    The section_ref is concatenated into the BM25 document so queries that
    reference citations literally ('§ 805', '1692c') hit the right chunk via
    keyword match -- the failure mode where a vector embedder treats '§ 805'
    as similar to other section markers across the statute. Cheap structural
    fallback; costs nothing.
    """
    with connect() as conn:
        chunks = get_all_chunks(conn, source=source)
    docs = [_tokenize(f"{c['section_ref']} {c['chunk_text']}") for c in chunks]
    log.info("BM25 index built for source=%s: %d chunks", source, len(chunks))
    return BM25Okapi(docs), chunks


def _get_bm25(source: str) -> tuple[BM25Okapi, list[dict]]:
    if source not in _BM25_CACHE:
        _BM25_CACHE[source] = _build_bm25_index(source)
    return _BM25_CACHE[source]


def reset_bm25_cache() -> None:
    """Force rebuild on next query. Call after re-ingesting; tests use this
    to swap in alternative fixtures."""
    _BM25_CACHE.clear()


# ---------------------------------------------------------------------------
# Retrieval stages
# ---------------------------------------------------------------------------


def vector_retrieve(conn, query: str, *, source: str, k: int) -> list[tuple[int, float]]:
    """pgvector cosine top-k. Voyage `input_type='query'` happens inside
    embed_query (asymmetric embedder; treat queries and docs differently).

    Assumes cosine_search returns dicts with at least `id` and `similarity`
    fields. If your db.py uses different key names, adjust here."""
    qvec = embed_query(query)
    rows = cosine_search(conn, qvec, source=source, limit=k)
    return [(r["id"], float(r["similarity"])) for r in rows]


def bm25_retrieve(query: str, *, source: str, k: int) -> list[tuple[int, float]]:
    """In-memory BM25 top-k from the cached index for this source."""
    bm25, chunks = _get_bm25(source)
    scores = bm25.get_scores(_tokenize(query))
    indexed = [(chunks[i]["id"], float(scores[i])) for i in range(len(chunks))]
    indexed.sort(key=lambda x: x[1], reverse=True)
    return indexed[:k]


def reciprocal_rank_fusion(
    rankings: list[list[tuple[int, float]]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """Cormack et al. 2009. Each input ranking contributes 1 / (k + rank) to
    each chunk's RRF score. Robust across the *score distributions* of the
    contributing retrievers -- only ranks matter, not raw scores.

    k=60 is the published default. Don't tune it in v0.1; tuning RRF k is a
    research question, not an engineering one."""
    rrf_scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, (chunk_id, _) in enumerate(ranking, start=1):
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


@lru_cache(maxsize=1)
def _cohere_client() -> cohere.ClientV2:
    """COHERE_API_KEY from env. Singleton; the client is HTTP-only and stateless."""
    return cohere.ClientV2()


# Cohere's Trial key is 10 RPM; production retrieval hits this during eval
# bursts. Backoff schedule below is calibrated to the trial-tier window: a
# 15-second initial sleep clears most rate-limit incidents, with two
# escalating retries for the worst case. Other transient failures (timeouts,
# 5xx) get the same treatment. Auth errors and malformed requests bubble up
# immediately — those aren't transient and silent retries would hide them.
_RERANK_MAX_RETRIES = 3
_RERANK_INITIAL_BACKOFF_S = 15.0


def _rerank_with_backoff(client, *, model: str, query: str, documents: list[str], top_n: int):
    """Call Cohere rerank with bounded exponential backoff on rate-limit errors."""
    backoff = _RERANK_INITIAL_BACKOFF_S
    last_exc: Optional[Exception] = None
    for attempt in range(_RERANK_MAX_RETRIES + 1):
        try:
            return client.rerank(
                model=model,
                query=query,
                documents=documents,
                top_n=top_n,
            )
        except cohere.TooManyRequestsError as exc:
            last_exc = exc
            if attempt == _RERANK_MAX_RETRIES:
                break
            jitter = random.uniform(0, backoff * 0.1)
            wait = backoff + jitter
            log.warning(
                "Cohere rate-limit (429) on rerank; sleeping %.1fs "
                "(attempt %d/%d)",
                wait, attempt + 1, _RERANK_MAX_RETRIES,
            )
            time.sleep(wait)
            backoff *= 2
    assert last_exc is not None
    raise last_exc


def rerank(query: str, chunks: list[dict]) -> list[tuple[int, float]]:
    """Cross-encoder rerank. Sends `section_ref: chunk_text` to the reranker
    so the model sees the structural context (consistent with the embedder's
    structural prefix at ingest)."""
    if not chunks:
        return []
    model = _rerank_model()
    client = _cohere_client()
    docs = [f"{c['section_ref']}: {c['chunk_text']}" for c in chunks]
    resp = _rerank_with_backoff(
        client,
        model=model,
        query=query,
        documents=docs,
        top_n=len(docs),  # rerank everything; we slice to final_top_k after
    )
    return [(chunks[r.index]["id"], float(r.relevance_score)) for r in resp.results]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def hybrid_retrieve(
    query: str,
    *,
    source: str = "fdcpa",
    config: Optional[dict] = None,
) -> RetrievalResult:
    """Six deterministic stages. The asymmetry is the architecture.

    1. Vector top-k          (pgvector, deterministic given pinned embedder)
    2. BM25 top-k            (deterministic given the corpus)
    3. RRF fusion            (deterministic given the two rankings)
    4. Hydrate top-N         (read from Postgres)
    5. Cross-encoder rerank  (deterministic given pinned reranker)
    6. Refusal check         (deterministic given the threshold)
    """
    cfg = config or _config()
    hyb = cfg["hybrid"]
    rrk = cfg["reranker"]
    refusal_cfg = cfg["refusal"]

    with connect() as conn:
        # 1: vector
        vector_hits = vector_retrieve(conn, query, source=source, k=hyb["vector_top_k"])

        # 2: BM25 (uses cached index per source; opens its own conn on first build)
        bm25_hits = bm25_retrieve(query, source=source, k=hyb["bm25_top_k"])

        # 3: RRF
        fused = reciprocal_rank_fusion(
            [vector_hits, bm25_hits],
            k=hyb["rrf_k_constant"],
        )
        if not fused:
            return RetrievalResult(
                query=query,
                chunks=[],
                refused=True,
                refusal_reason=(
                    "no candidates from RRF (corpus empty or both retrievers "
                    "returned nothing)"
                ),
                refusal_message=refusal_cfg["refusal_message"],
            )

        # 4: hydrate top-N for the reranker
        rerank_input_ids = [cid for cid, _ in fused[: rrk["candidates"]]]
        rerank_chunks = get_chunks_by_ids(conn, rerank_input_ids)

    # 5: rerank (no DB needed, conn closed)
    reranked = rerank(query, rerank_chunks)
    top_score = reranked[0][1] if reranked else 0.0

    # 6: refusal check -- first-class output, NOT an error case
    threshold = refusal_cfg["rerank_score_threshold"]
    if top_score < threshold:
        return RetrievalResult(
            query=query,
            chunks=[],
            refused=True,
            refusal_reason=(
                f"top reranker score {top_score:.3f} below threshold "
                f"{threshold:.3f}"
            ),
            refusal_message=refusal_cfg["refusal_message"],
            top_rerank_score=top_score,
        )

    # Build final output, carrying full per-stage score history for audit
    chunks_by_id = {c["id"]: c for c in rerank_chunks}
    vec_by_id = dict(vector_hits)
    bm25_by_id = dict(bm25_hits)
    rrf_by_id = dict(fused)

    final = []
    for chunk_id, rerank_score in reranked[: rrk["return_top_k"]]:
        c = chunks_by_id[chunk_id]
        final.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                source=c["source"],
                section_ref=c["section_ref"],
                chunk_text=c["chunk_text"],
                metadata=c["metadata"],
                vector_score=vec_by_id.get(chunk_id),
                bm25_score=bm25_by_id.get(chunk_id),
                rrf_score=rrf_by_id.get(chunk_id),
                rerank_score=rerank_score,
            )
        )

    return RetrievalResult(
        query=query,
        chunks=final,
        refused=False,
        top_rerank_score=top_score,
    )
