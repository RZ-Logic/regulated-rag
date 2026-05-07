"""
Hour 7: generation with citation grounding and refusal as first-class outputs.

Where the LLM is in this module: ONE place. The Anthropic Messages API call
in `_call_anthropic`. Everything before and after is deterministic.

Architecture (the asymmetry is the point):

  Input-side deterministic checks
  ┌─────────────────────────────────────┐
  │ 1. retrieval threshold (hour 5)     │ → refuse if top rerank < threshold
  │ 2. named-regulation pre-check (h7)  │ → refuse if query names out-of-corpus reg
  └─────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │  STOCHASTIC STAGE    │
         │  Anthropic Sonnet 4.6│
         │  tool_choice=answer  │
         │  temperature=0       │
         └──────────────────────┘
                    │
                    ▼
  Output-side deterministic checks
  ┌─────────────────────────────────────┐
  │ 3. citation grounding validator     │ → refuse if any cited chunk_id not in
  │                                     │   retrieved set, or claims w/o citations
  │ 4. generator self-refusal           │ → respect answered=false from tool call
  └─────────────────────────────────────┘

Refusal is a typed first-class output via RefusalReason. The README's
"Where is the LLM?" table maps these stages 1:1 with this module's structure.

Reproducibility posture:
  - Model alias pinned in models.yml (anthropic publishes no dated snapshot
    for sonnet-4-6 on direct API per May 2026 docs)
  - temperature=0 (still slightly non-deterministic API-side; alias pin +
    request_id capture is the audit trail)
  - Every API response's request_id logged
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

import anthropic
import yaml

from regulated_rag.retrieval import RetrievalResult, RetrievedChunk, hybrid_retrieve

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Refusal taxonomy
# ---------------------------------------------------------------------------


class RefusalReason(str, Enum):
    """The four refusal paths in the v0.1 architecture. Each is a deterministic
    check; none is the LLM judging itself."""

    LOW_RETRIEVAL_CONFIDENCE = "low_retrieval_confidence"
    NAMED_REGULATION_NOT_IN_CORPUS = "named_regulation_not_in_corpus"
    GENERATOR_DECLINED = "generator_declined"
    CITATION_GROUNDING_FAILED = "citation_grounding_failed"


# Default user-facing messages per refusal reason. Keep neutral; the audit
# trail carries the technical specifics.
_DEFAULT_REFUSAL_MESSAGES: dict[RefusalReason, str] = {
    RefusalReason.LOW_RETRIEVAL_CONFIDENCE: (
        "The corpus does not contain sufficient information to answer this "
        "question with confidence."
    ),
    RefusalReason.NAMED_REGULATION_NOT_IN_CORPUS: (
        "This question references a regulation outside the current corpus. "
        "The corpus contains the Fair Debt Collection Practices Act (FDCPA) only."
    ),
    RefusalReason.GENERATOR_DECLINED: (
        "The retrieved sections do not directly address this question."
    ),
    RefusalReason.CITATION_GROUNDING_FAILED: (
        "The system could not produce a citation-grounded answer for this question."
    ),
}


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    """One factual statement, citing one or more retrieved chunks. Every
    claim must cite at least one chunk_id from the retrieved set; the
    validator enforces this."""

    text: str
    chunk_ids: list[int]


@dataclass
class GenerationResult:
    """Pipeline output. Either answered (with claims) or refused (with reason).
    The full audit trail is preserved either way -- request_id, retrieved
    chunk ids, model pin, elapsed -- so any downstream auditor can verify
    what the system saw and what it returned."""

    query: str
    answered: bool
    claims: list[Claim] = field(default_factory=list)
    refused: bool = False
    refusal_reason: Optional[RefusalReason] = None
    refusal_message: Optional[str] = None
    refusal_detail: Optional[str] = None  # technical detail for audit/log
    detected_regulation: Optional[str] = None  # set when reason=NAMED_REGULATION_NOT_IN_CORPUS
    # Audit trail
    retrieved_chunk_ids: list[int] = field(default_factory=list)
    retrieved_top_rerank_score: Optional[float] = None
    model: Optional[str] = None
    request_id: Optional[str] = None
    elapsed_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Out-of-corpus regulation patterns (v0.1: corpus = ['fdcpa'])
# ---------------------------------------------------------------------------
# These are explicit named regulations NOT in the v0.1 corpus. When a query
# mentions one of these by name, the system refuses BEFORE calling the LLM:
# the threshold-based retrieval refusal cannot catch this case (hour 6 finding
# adjacent-regf), because retrieval can return high-rerank FDCPA chunks for
# a query about a different regulation.
#
# v0.2 implications: when the corpus expands (e.g., adds Reg F), remove that
# entry from this list. The list is "things explicitly NOT in corpus" not
# "things to refuse on principle."
#
# The patterns are intentionally conservative -- we want false-negatives
# (missing some named regulation) over false-positives (refusing legit FDCPA
# queries). The cooperative path lives in the system prompt; this is the
# enforcement boundary.

OUT_OF_CORPUS_REGULATIONS: list[tuple[str, str]] = [
    # CFPB / FDCPA-adjacent
    (r"\bregulation\s+f\b", "Regulation F"),
    (r"\breg\.?\s+f\b", "Regulation F"),
    (r"\b12\s*c\.?f\.?r\.?\s*(?:part\s+)?1006\b", "12 CFR Part 1006 (Regulation F)"),
    # Privacy / data protection
    (r"\bgdpr\b", "GDPR"),
    (r"\bccpa\b", "CCPA"),
    (r"\bcpra\b", "CPRA"),
    # Other consumer-finance statutes
    (r"\btila\b", "Truth in Lending Act (TILA)"),
    (r"\btruth\s+in\s+lending\b", "Truth in Lending Act"),
    (r"\bfcra\b", "Fair Credit Reporting Act (FCRA)"),
    (r"\bfair\s+credit\s+reporting\b", "Fair Credit Reporting Act"),
    (r"\becoa\b", "Equal Credit Opportunity Act (ECOA)"),
    (r"\bequal\s+credit\s+opportunity\b", "Equal Credit Opportunity Act"),
    # Securities
    (r"\bsec\s+rule", "SEC rules"),
    (r"\bsecurities\s+exchange\s+act\b", "Securities Exchange Act"),
    # State/EWA (deferred from v0.1 corpus per BUILD-LOG)
    (r"\bcalifornia\s+ewa\b", "California Earned Wage Access framework"),
    (r"\bearned\s+wage\s+access\b", "Earned Wage Access regulations"),
]


# Compile once
_OUT_OF_CORPUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), name) for p, name in OUT_OF_CORPUS_REGULATIONS
]


def pre_generation_corpus_check(query: str) -> Optional[str]:
    """Returns the human-readable name of the FIRST detected out-of-corpus
    regulation, or None if no match. v0.1: assumes corpus=['fdcpa']. When
    corpus expands, prune OUT_OF_CORPUS_REGULATIONS accordingly.

    This is the deterministic enforcement boundary for the hour-6 finding
    that threshold-based retrieval refusal cannot catch query-intent vs
    corpus-source mismatch. If this returns a string, the system refuses
    before any LLM call."""
    for pattern, name in _OUT_OF_CORPUS_PATTERNS:
        if pattern.search(query):
            return name
    return None


# ---------------------------------------------------------------------------
# Generation tool (Anthropic tool_use schema)
# ---------------------------------------------------------------------------
# Forcing tool_choice = {"type": "tool", "name": "answer"} guarantees the
# model emits structured output matching this schema. No JSON parsing fragility,
# no markdown-around-JSON failures. The schema IS the contract.

ANSWER_TOOL: dict = {
    "name": "answer",
    "description": (
        "Submit your answer or refusal to the user's question, with claim-level "
        "citations to specific chunk_ids from the provided sources. Every factual "
        "claim must cite at least one chunk_id you actually saw in the provided "
        "chunks; do not invent chunk_ids."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answered": {
                "type": "boolean",
                "description": (
                    "true if you can answer the question from the provided chunks; "
                    "false if the chunks do not contain enough information or if "
                    "the question asks about a regulation not in the corpus."
                ),
            },
            "refusal_reason": {
                "type": "string",
                "description": (
                    "Required when answered=false. Brief technical reason "
                    "(e.g., 'chunks address consumer communication but not "
                    "third-party disclosure', 'question asks about Regulation F "
                    "which is not in the FDCPA-only corpus')."
                ),
            },
            "claims": {
                "type": "array",
                "description": (
                    "List of claims that together answer the question. Empty "
                    "when answered=false. Each claim is a single self-contained "
                    "statement (one or two sentences) with chunk_id citations."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": (
                                "The claim text. Paraphrase or quote from the "
                                "provided chunks; do not introduce facts outside them."
                            ),
                        },
                        "chunk_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": (
                                "chunk_ids (integers) supporting this claim. Must be "
                                "non-empty and must reference chunks that actually "
                                "appear in the provided sources."
                            ),
                        },
                    },
                    "required": ["text", "chunk_ids"],
                },
            },
        },
        "required": ["answered", "claims"],
    },
}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an information-retrieval assistant for the Fair Debt Collection \
Practices Act (FDCPA), 15 U.S.C. §§ 1692–1692p. Your only knowledge source \
is the chunks provided in each user message. You do not draw on prior \
knowledge of the FDCPA or any other regulation, even if you are confident.

You must respond by calling the `answer` tool. The tool's schema requires \
structured claims with chunk_id citations.

Hard rules:
1. Every factual claim must cite at least one chunk_id that appears in the \
provided chunks. Do not cite chunk_ids you did not see.
2. If the question asks about a regulation OTHER THAN the FDCPA \
(for example: Regulation F, CFPB Reg F, 12 CFR Part 1006, GDPR, CCPA, TILA, \
FCRA, ECOA, SEC rules, state-specific frameworks), set answered=false and \
explain that the corpus contains FDCPA only.
3. If the provided chunks do not contain enough information to answer the \
question, set answered=false and briefly state what is missing. Do not \
speculate or use general knowledge.
4. Quote or paraphrase the chunks. Do not introduce facts not present in them.
5. Each claim should be a single self-contained statement (one or two \
sentences). Long, multi-fact sentences should be split into multiple claims, \
each with its own citations.
6. The chunk_ids field for each claim must be a non-empty list of integers \
referencing chunk_id values exactly as they appear in the <chunk id="..."> \
tags of the provided sources.
"""


def _build_user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    """User-message body: the question plus the retrieved chunks formatted
    as XML-tagged blocks. XML is the documented Anthropic preference for
    structured context; chunk_id is exposed as the tag's id attribute so the
    model can cite it cleanly."""
    parts = ["<sources>"]
    for c in chunks:
        # Strip nothing; let the model see the chunk as it was indexed.
        parts.append(
            f'<chunk id="{c.chunk_id}" section_ref="{c.section_ref}" source="{c.source}">'
        )
        parts.append(c.chunk_text)
        parts.append("</chunk>")
    parts.append("</sources>")
    parts.append("")
    parts.append(f"<question>{query}</question>")
    parts.append("")
    parts.append(
        "Answer the question using only the sources above. Call the `answer` "
        "tool. Every claim must cite at least one chunk_id from the sources."
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Output-side validator
# ---------------------------------------------------------------------------


def _validate_citations(
    claims: list[Claim],
    retrieved_chunk_ids: set[int],
) -> tuple[bool, str]:
    """Three checks:
    - claims list is non-empty (when generator says answered=true)
    - every claim has at least one chunk_id (no orphan claims)
    - every cited chunk_id appears in the retrieved set (no fabricated citations)

    Returns (is_valid, detail). detail is empty when valid; describes the
    first violation found otherwise. Defensive enough to surface multiple
    failure modes for the audit log without being clever about it."""
    if not claims:
        return False, "claims list is empty despite answered=true"

    fabricated: list[int] = []
    orphans: list[int] = []  # indices of claims with no chunk_ids

    for i, claim in enumerate(claims):
        if not claim.chunk_ids:
            orphans.append(i)
        for cid in claim.chunk_ids:
            if cid not in retrieved_chunk_ids:
                fabricated.append(cid)

    if orphans:
        return False, f"claims without citations at indices {orphans}"
    if fabricated:
        # dedupe while preserving order for readability
        seen = set()
        unique_fab = [x for x in fabricated if not (x in seen or seen.add(x))]
        return (
            False,
            f"cited chunk_ids not in retrieved set: {unique_fab} "
            f"(retrieved set: {sorted(retrieved_chunk_ids)})",
        )
    return True, ""


# ---------------------------------------------------------------------------
# Anthropic call
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _models_config() -> dict:
    with Path("config/models.yml").open() as f:
        return yaml.safe_load(f)


def _generator_config() -> dict:
    """Pull generator block from models.yml. Tolerant of either flat or
    nested shapes (the same convention retrieval.py uses for cohere)."""
    cfg = _models_config()
    gen = cfg.get("generator")
    if not isinstance(gen, dict):
        raise ValueError("models.yml missing 'generator' block")
    return gen


@lru_cache(maxsize=1)
def _anthropic_client() -> anthropic.Anthropic:
    """Singleton client. ANTHROPIC_API_KEY from env. Stateless; safe to cache."""
    return anthropic.Anthropic()


def _call_anthropic(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float,
) -> tuple[anthropic.types.Message, Optional[str]]:
    """The single LLM call in the entire pipeline. Returns (response,
    request_id). request_id is the Anthropic-side identifier captured for
    audit reproducibility -- alias pin tells you WHICH model snapshot served
    the request, request_id lets Anthropic look up the exact one if needed."""
    client = _anthropic_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[ANSWER_TOOL],
        tool_choice={"type": "tool", "name": "answer"},
    )
    # Anthropic SDK exposes _request_id on the response; if absent in the
    # installed SDK version, falls back to None and the audit trail loses
    # the request_id but everything else is preserved.
    request_id = getattr(response, "_request_id", None)
    return response, request_id


def _extract_tool_call(response: anthropic.types.Message) -> Optional[dict]:
    """Pull the answer-tool input from the response. With tool_choice forcing
    the answer tool, the response.content should always include exactly one
    tool_use block. Defensive: returns None if not found, lets caller decide."""
    for block in response.content:
        if block.type == "tool_use" and block.name == "answer":
            return block.input  # already a dict per SDK
    return None


# ---------------------------------------------------------------------------
# Public pipeline
# ---------------------------------------------------------------------------


def generate(query: str, *, source: str = "fdcpa") -> GenerationResult:
    """High-level: query -> retrieval -> generation. Convenience wrapper for
    callers that don't need to handle retrieval results separately."""
    retrieval_result = hybrid_retrieve(query, source=source)
    return generate_from_retrieval(query, retrieval_result)


def generate_from_retrieval(
    query: str,
    retrieval_result: RetrievalResult,
) -> GenerationResult:
    """Run the generation pipeline on an already-retrieved result. Use this
    for evals where retrieval is computed once and shared, or for tests
    that want to inject a synthetic RetrievalResult."""
    t0 = time.perf_counter()

    # ---- Input-side check 1: retrieval refusal (passthrough) ----------
    if retrieval_result.refused:
        return GenerationResult(
            query=query,
            answered=False,
            refused=True,
            refusal_reason=RefusalReason.LOW_RETRIEVAL_CONFIDENCE,
            refusal_message=_DEFAULT_REFUSAL_MESSAGES[
                RefusalReason.LOW_RETRIEVAL_CONFIDENCE
            ],
            refusal_detail=retrieval_result.refusal_reason,
            retrieved_top_rerank_score=retrieval_result.top_rerank_score,
            elapsed_seconds=round(time.perf_counter() - t0, 3),
        )

    # ---- Input-side check 2: named-regulation pre-check (hour 7 NEW) --
    detected = pre_generation_corpus_check(query)
    if detected is not None:
        log.info("pre-gen refusal: detected out-of-corpus regulation '%s'", detected)
        return GenerationResult(
            query=query,
            answered=False,
            refused=True,
            refusal_reason=RefusalReason.NAMED_REGULATION_NOT_IN_CORPUS,
            refusal_message=_DEFAULT_REFUSAL_MESSAGES[
                RefusalReason.NAMED_REGULATION_NOT_IN_CORPUS
            ],
            refusal_detail=f"matched named regulation: {detected}",
            detected_regulation=detected,
            retrieved_chunk_ids=[c.chunk_id for c in retrieval_result.chunks],
            retrieved_top_rerank_score=retrieval_result.top_rerank_score,
            elapsed_seconds=round(time.perf_counter() - t0, 3),
        )

    # ---- Stochastic stage --------------------------------------------
    gen_cfg = _generator_config()
    model = gen_cfg["model"]
    max_tokens = int(gen_cfg.get("max_tokens", 1024))
    temperature = float(gen_cfg.get("temperature", 0.0))

    user_prompt = _build_user_prompt(query, retrieval_result.chunks)
    log.info(
        "calling anthropic: model=%s max_tokens=%d temp=%.2f chunks=%d",
        model, max_tokens, temperature, len(retrieval_result.chunks),
    )
    response, request_id = _call_anthropic(
        SYSTEM_PROMPT,
        user_prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    log.info("anthropic response: request_id=%s stop_reason=%s",
             request_id, response.stop_reason)

    tool_input = _extract_tool_call(response)
    if tool_input is None:
        # Defensive: tool_choice forces it, so this should never happen,
        # but if the SDK behavior changes we want a clean refusal not a crash.
        return GenerationResult(
            query=query,
            answered=False,
            refused=True,
            refusal_reason=RefusalReason.CITATION_GROUNDING_FAILED,
            refusal_message=_DEFAULT_REFUSAL_MESSAGES[
                RefusalReason.CITATION_GROUNDING_FAILED
            ],
            refusal_detail="no tool_use block in response",
            retrieved_chunk_ids=[c.chunk_id for c in retrieval_result.chunks],
            retrieved_top_rerank_score=retrieval_result.top_rerank_score,
            model=model,
            request_id=request_id,
            elapsed_seconds=round(time.perf_counter() - t0, 3),
        )

    answered = bool(tool_input.get("answered", False))
    raw_claims = tool_input.get("claims", [])
    claims = [
        Claim(text=str(c.get("text", "")), chunk_ids=list(c.get("chunk_ids", [])))
        for c in raw_claims
    ]
    retrieved_ids_set = {c.chunk_id for c in retrieval_result.chunks}
    retrieved_ids_list = [c.chunk_id for c in retrieval_result.chunks]

    # ---- Output-side check: generator self-refusal -------------------
    if not answered:
        gen_reason = str(tool_input.get("refusal_reason") or "no reason given")
        log.info("generator declined: %s", gen_reason)
        return GenerationResult(
            query=query,
            answered=False,
            refused=True,
            refusal_reason=RefusalReason.GENERATOR_DECLINED,
            refusal_message=_DEFAULT_REFUSAL_MESSAGES[RefusalReason.GENERATOR_DECLINED],
            refusal_detail=gen_reason,
            retrieved_chunk_ids=retrieved_ids_list,
            retrieved_top_rerank_score=retrieval_result.top_rerank_score,
            model=model,
            request_id=request_id,
            elapsed_seconds=round(time.perf_counter() - t0, 3),
        )

    # ---- Output-side check: citation grounding -----------------------
    is_valid, detail = _validate_citations(claims, retrieved_ids_set)
    if not is_valid:
        log.warning("citation grounding failed: %s", detail)
        return GenerationResult(
            query=query,
            answered=False,
            refused=True,
            refusal_reason=RefusalReason.CITATION_GROUNDING_FAILED,
            refusal_message=_DEFAULT_REFUSAL_MESSAGES[
                RefusalReason.CITATION_GROUNDING_FAILED
            ],
            refusal_detail=detail,
            retrieved_chunk_ids=retrieved_ids_list,
            retrieved_top_rerank_score=retrieval_result.top_rerank_score,
            model=model,
            request_id=request_id,
            elapsed_seconds=round(time.perf_counter() - t0, 3),
        )

    # ---- All checks passed -------------------------------------------
    return GenerationResult(
        query=query,
        answered=True,
        claims=claims,
        refused=False,
        retrieved_chunk_ids=retrieved_ids_list,
        retrieved_top_rerank_score=retrieval_result.top_rerank_score,
        model=model,
        request_id=request_id,
        elapsed_seconds=round(time.perf_counter() - t0, 3),
    )


# ---------------------------------------------------------------------------
# Serialization helper for runs/ logging
# ---------------------------------------------------------------------------


def result_to_dict(result: GenerationResult) -> dict:
    """JSON-friendly dict for runs/ archival. Enums become their values;
    nested Claims become dicts."""
    d = asdict(result)
    if d.get("refusal_reason") is not None:
        d["refusal_reason"] = result.refusal_reason.value if result.refusal_reason else None
    return d
