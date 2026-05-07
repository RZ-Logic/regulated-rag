"""
Hour 8 — eval harness for regulated-rag v0.1.

Reads eval/v0_1.yml. For each query: runs the full retrieval+generation
pipeline, scores deterministically against the expected fields, archives
per-query transcripts to runs/baseline-v0.1.jsonl plus an aggregate summary
to runs/baseline-v0.1.json. Prints a human-readable report card to stdout.

Metrics reported (per BUILD-LOG hour-8 methodology lock):

  Deterministic (machine-checkable, no judge):
    - retrieval_precision_at_5: any expected citation in retrieved top-5
    - any_expected_cited:       any expected citation in cited set (headline
                                read for "did the system get it right")
    - citation_recall:          (cited ∩ expected) / |expected|
    - citation_precision:       (cited ∩ expected) / |cited|
    - refusal_correctness:      did refusal_reason match expected
                                (for OOC queries; null for in-corpus)
    - citation_grounding_failed_count: should be 0 on the in-corpus set;
                                non-zero is a quality regression flag

  Hand-graded (transcripts logged, graded post-run):
    - faithfulness:    claim text follows from cited chunk's text
    - answer_relevance: answer addresses the question asked

  Operational:
    - latency p50 / p95
    - refusal_path_distribution

Threshold posture: 0.30 was chosen empirically during hour 5 smoke and hour
6 edge probes — the de-facto dev set. v0.1 does not perform a formal
dev/test split; doing so on N=20 with a placeholder threshold would be
methodological theater. v0.2 with a larger eval set warrants the split.

LLM-as-judge posture: not used in v0.1. Adding an LLM-judge to the eval
pipeline puts another stochastic stage in the measurement layer — the
layer that is supposed to be the audit trail. Hand-grading ~30 claims
takes ~20 min and matches finance-agent-evals' "read the transcripts"
rule. v0.2 with a larger eval set may justify LLM-judge with the judge
model alias-pinned and request_ids logged.

Citation match posture: exact section_ref match. § 805 cited when expected
was § 805(a)(1) is a citation-grain mismatch worth flagging. v0.2 may add
hierarchical matching as a feature with a documented relaxation rule.

Usage:
  python scripts/eval_v0_1.py
  python scripts/eval_v0_1.py --filter fdcpa-001        # one query
  python scripts/eval_v0_1.py --filter fdcpa-           # all in-corpus
  python scripts/eval_v0_1.py --dry-run                 # validate YAML only
  python scripts/eval_v0_1.py --output-dir runs/exp1    # alternate output
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Windows consoles default to cp1252; the eval set is UTF-8 (regulatory
# glyphs like § are non-ASCII). Force UTF-8 on stdout/stderr so display
# matches the underlying strings. File reads/writes also pin encoding="utf-8"
# below; this is the display side of the same fix.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import yaml
from dotenv import load_dotenv

load_dotenv()  # entry-point owns dotenv per hour-5 decision

from regulated_rag.generation import (  # noqa: E402
    GenerationResult,
    RefusalReason,
    generate_from_retrieval,
    result_to_dict,
)
from regulated_rag.retrieval import RetrievedChunk, hybrid_retrieve  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("eval-h8")


# ---------------------------------------------------------------------------
# Paths & config loading
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_PATH = REPO_ROOT / "eval" / "v0_1.yml"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "runs"
MODELS_PATH = REPO_ROOT / "config" / "models.yml"
RETRIEVAL_PATH = REPO_ROOT / "config" / "retrieval.yml"


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_eval_set(path: Path) -> list[dict]:
    """Load and minimally validate the eval YAML. Hard-fail if a query is
    structurally invalid — partial-eval-on-malformed-input is a footgun."""
    data = _load_yaml(path)
    if "queries" not in data or not isinstance(data["queries"], list):
        raise ValueError(f"{path} must have a top-level 'queries' list")
    queries = data["queries"]
    seen_ids: set[str] = set()
    valid_categories = {
        "in_corpus",
        "ooc_low_retrieval",
        "ooc_named_regulation",
        "ooc_generator_declined",
    }
    valid_reasons = {r.value.upper() for r in RefusalReason} | {None}
    for i, q in enumerate(queries):
        if "id" not in q:
            raise ValueError(f"queries[{i}] missing 'id'")
        if q["id"] in seen_ids:
            raise ValueError(f"duplicate query id: {q['id']}")
        seen_ids.add(q["id"])
        if q.get("category") not in valid_categories:
            raise ValueError(f"{q['id']}: invalid category {q.get('category')!r}")
        if "expected" not in q:
            raise ValueError(f"{q['id']}: missing 'expected'")
        exp = q["expected"]
        # Normalize refusal_reason to uppercase string or None for comparison
        rr = exp.get("refusal_reason")
        if rr is not None and rr not in valid_reasons:
            raise ValueError(f"{q['id']}: invalid refusal_reason {rr!r}")
    return queries


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _cited_section_refs(
    result: GenerationResult, retrieved: list[RetrievedChunk]
) -> list[str]:
    """Map cited chunk_ids back to section_refs using the retrieved set.
    A cited chunk_id not in the retrieved set is a CITATION_GROUNDING_FAILED
    case which the generation pipeline already catches; if we get here, the
    map should be complete."""
    id_to_ref = {c.chunk_id: c.section_ref for c in retrieved}
    refs: list[str] = []
    for claim in result.claims:
        for cid in claim.chunk_ids:
            ref = id_to_ref.get(cid)
            if ref is not None:
                refs.append(ref)
    return refs


def _score_in_corpus(
    expected: dict,
    result: GenerationResult,
    retrieved: list[RetrievedChunk],
) -> dict[str, Any]:
    """Score deterministically for an in-corpus query.
    Returns a dict ready to embed in the per-query transcript."""
    expected_cites: set[str] = set(expected.get("citations") or [])
    retrieved_refs: set[str] = {c.section_ref for c in retrieved}
    cited_refs_list = _cited_section_refs(result, retrieved)
    cited_refs: set[str] = set(cited_refs_list)

    # If the system refused on an in-corpus query, all retrieval/citation
    # metrics are null but we still record the refusal as a finding.
    if result.refused:
        return {
            "outcome": "refused",
            "refusal_reason": (
                result.refusal_reason.value if result.refusal_reason else None
            ),
            "expected_outcome": "answered",
            "passed": False,
            "retrieval_precision_at_5": (
                bool(expected_cites & retrieved_refs) if expected_cites else None
            ),
            "any_expected_cited": False,
            "citation_recall": None,
            "citation_precision": None,
            "cited_section_refs": [],
            "expected_citations": sorted(expected_cites),
            "retrieved_section_refs_top5": [c.section_ref for c in retrieved[:5]],
        }

    # Answered path
    intersection = cited_refs & expected_cites
    recall = len(intersection) / len(expected_cites) if expected_cites else None
    precision = len(intersection) / len(cited_refs) if cited_refs else None
    return {
        "outcome": "answered",
        "expected_outcome": "answered",
        "passed": bool(intersection),  # any expected cited = passed for headline
        "retrieval_precision_at_5": (
            bool(expected_cites & retrieved_refs) if expected_cites else None
        ),
        "any_expected_cited": bool(intersection),
        "citation_recall": recall,
        "citation_precision": precision,
        "cited_section_refs": cited_refs_list,  # list, preserves duplicates
        "expected_citations": sorted(expected_cites),
        "retrieved_section_refs_top5": [c.section_ref for c in retrieved[:5]],
    }


def _score_ooc(
    expected: dict,
    result: GenerationResult,
) -> dict[str, Any]:
    """Score deterministically for an out-of-corpus query.
    Refusal correctness is the sole pass criterion."""
    # YAML stores refusal_reason in upper-case enum-NAME form (e.g.
    # "LOW_RETRIEVAL_CONFIDENCE"). The enum's .value is lower-case underscore
    # ("low_retrieval_confidence"). Compare on .name for symmetry with the
    # YAML representation.
    expected_reason: Optional[str] = expected.get("refusal_reason")
    expected_reason_norm = expected_reason.upper() if expected_reason else None
    actual_reason_norm = (
        result.refusal_reason.name if result.refusal_reason else None
    )

    detected_match: Optional[bool] = None
    if expected.get("detected_regulation") is not None:
        detected_match = (
            result.detected_regulation == expected["detected_regulation"]
        )

    return {
        "outcome": "refused" if result.refused else "answered",
        "expected_outcome": "refused",
        "passed": (
            result.refused and actual_reason_norm == expected_reason_norm
        ),
        "expected_refusal_reason": expected_reason_norm,
        "actual_refusal_reason": actual_reason_norm,
        "expected_detected_regulation": expected.get("detected_regulation"),
        "actual_detected_regulation": result.detected_regulation,
        "detected_regulation_match": detected_match,
        "top_rerank_score_at_refusal": result.retrieved_top_rerank_score,
    }


# ---------------------------------------------------------------------------
# Per-query runner
# ---------------------------------------------------------------------------


def _run_one(query_spec: dict) -> dict:
    """Run a single query through retrieval+generation, score it, return the
    transcript dict ready for JSONL emission."""
    qid = query_spec["id"]
    category = query_spec["category"]
    query_text = query_spec["query"]
    expected = query_spec["expected"]

    log.info("query %s [%s]: %s", qid, category, query_text)
    t0 = time.perf_counter()
    error: Optional[str] = None
    result: Optional[GenerationResult] = None
    retrieved: list[RetrievedChunk] = []

    try:
        retrieval_result = hybrid_retrieve(query_text)
        retrieved = list(retrieval_result.chunks)
        result = generate_from_retrieval(query_text, retrieval_result)
    except Exception as exc:  # per-query try/except — partial results are useful
        log.exception("query %s raised", qid)
        error = repr(exc)

    elapsed = round(time.perf_counter() - t0, 3)

    transcript: dict[str, Any] = {
        "id": qid,
        "category": category,
        "query": query_text,
        "expected": expected,
        "notes": query_spec.get("notes"),
        "elapsed_seconds": elapsed,
        "error": error,
    }

    if error is not None or result is None:
        transcript["scores"] = {
            "outcome": "error",
            "passed": False,
        }
        return transcript

    # Full result for the audit trail
    transcript["result"] = result_to_dict(result)
    # Retrieval audit (top-5 with rerank scores)
    transcript["retrieved_top5"] = [
        {
            "chunk_id": c.chunk_id,
            "section_ref": c.section_ref,
            "rerank_score": getattr(c, "rerank_score", None),
            "rrf_score": getattr(c, "rrf_score", None),
            "vector_score": getattr(c, "vector_score", None),
            "bm25_score": getattr(c, "bm25_score", None),
        }
        for c in retrieved[:5]
    ]

    # Score by category bucket
    if category == "in_corpus":
        transcript["scores"] = _score_in_corpus(expected, result, retrieved)
    else:
        transcript["scores"] = _score_ooc(expected, result)

    return transcript


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    # Linear interpolation
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _aggregate(transcripts: list[dict]) -> dict[str, Any]:
    by_cat: dict[str, list[dict]] = {}
    for t in transcripts:
        by_cat.setdefault(t["category"], []).append(t)

    in_corpus = by_cat.get("in_corpus", [])
    ooc_all = [
        t for t in transcripts if t["category"].startswith("ooc_")
    ]

    # In-corpus deterministic metrics (only over non-error rows)
    ic_clean = [t for t in in_corpus if t["scores"].get("outcome") != "error"]
    ic_n = len(ic_clean)
    n_ret_p5 = sum(1 for t in ic_clean if t["scores"].get("retrieval_precision_at_5"))
    n_any_cited = sum(1 for t in ic_clean if t["scores"].get("any_expected_cited"))
    recalls = [
        t["scores"]["citation_recall"]
        for t in ic_clean
        if t["scores"].get("citation_recall") is not None
    ]
    precisions = [
        t["scores"]["citation_precision"]
        for t in ic_clean
        if t["scores"].get("citation_precision") is not None
    ]
    cgf_count = sum(
        1
        for t in ic_clean
        if t["scores"].get("refusal_reason") == RefusalReason.CITATION_GROUNDING_FAILED.value
    )

    # OOC refusal correctness
    ooc_clean = [t for t in ooc_all if t["scores"].get("outcome") != "error"]
    ooc_n = len(ooc_clean)
    n_ooc_pass = sum(1 for t in ooc_clean if t["scores"].get("passed"))
    by_path: dict[str, dict[str, int]] = {}
    for t in ooc_clean:
        path = t["expected"]["refusal_reason"]
        if path not in by_path:
            by_path[path] = {"n": 0, "passed": 0}
        by_path[path]["n"] += 1
        if t["scores"].get("passed"):
            by_path[path]["passed"] += 1

    # Operational
    latencies = [
        t["elapsed_seconds"]
        for t in transcripts
        if t.get("elapsed_seconds") is not None and t.get("error") is None
    ]
    refusal_dist: dict[str, int] = {"answered": 0}
    for t in transcripts:
        if t.get("error"):
            continue
        result = t.get("result", {})
        if result.get("refused"):
            r = result.get("refusal_reason") or "unknown"
            refusal_dist[r] = refusal_dist.get(r, 0) + 1
        elif result.get("answered"):
            refusal_dist["answered"] += 1

    return {
        "n_queries_total": len(transcripts),
        "n_queries_in_corpus": len(in_corpus),
        "n_queries_ooc": len(ooc_all),
        "n_errors": sum(1 for t in transcripts if t.get("error")),
        "deterministic": {
            "in_corpus": {
                "n": ic_n,
                "retrieval_precision_at_5": f"{n_ret_p5}/{ic_n}",
                "any_expected_cited": f"{n_any_cited}/{ic_n}",
                "citation_recall_mean": (
                    round(statistics.fmean(recalls), 3) if recalls else None
                ),
                "citation_precision_mean": (
                    round(statistics.fmean(precisions), 3) if precisions else None
                ),
                "citation_grounding_failed_count": cgf_count,
            },
            "ooc": {
                "n": ooc_n,
                "refusal_correctness_overall": f"{n_ooc_pass}/{ooc_n}",
                "by_path": {
                    p: f"{v['passed']}/{v['n']}" for p, v in sorted(by_path.items())
                },
            },
        },
        "operational": {
            "latency_p50_seconds": round(_percentile(latencies, 0.50) or 0.0, 3),
            "latency_p95_seconds": round(_percentile(latencies, 0.95) or 0.0, 3),
            "refusal_path_distribution": dict(
                sorted(refusal_dist.items(), key=lambda kv: (-kv[1], kv[0]))
            ),
        },
        "hand_grading": {
            "instructions": (
                "Faithfulness and answer relevance require reading "
                "transcripts at runs/baseline-v0.1.jsonl. Per finance-agent-evals' "
                "'read the transcripts' rule. Grade results into "
                "runs/baseline-v0.1-handgrading.json."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(transcripts: list[dict], summary: dict, config_snap: dict) -> None:
    line = "=" * 88
    print()
    print(line)
    print("regulated-rag v0.1 — eval results")
    print(line)
    print(f"ran:    {summary['ran_at']}")
    print(
        f"models: voyage={config_snap.get('voyage')}  "
        f"rerank={config_snap.get('cohere')}  "
        f"gen={config_snap.get('anthropic')}"
    )
    print(
        f"params: threshold={config_snap.get('threshold')}  "
        f"vector_top_k={config_snap.get('vector_top_k')}  "
        f"bm25_top_k={config_snap.get('bm25_top_k')}  "
        f"return_top_k={config_snap.get('return_top_k')}"
    )
    print()

    print(
        f"n queries: {summary['n_queries_total']} "
        f"(in_corpus={summary['n_queries_in_corpus']}, ooc={summary['n_queries_ooc']}, "
        f"errors={summary['n_errors']})"
    )
    print()

    det = summary["deterministic"]
    print("DETERMINISTIC METRICS")
    print(f"  in-corpus (n={det['in_corpus']['n']}):")
    print(f"    retrieval_precision_at_5:        {det['in_corpus']['retrieval_precision_at_5']}")
    print(f"    any_expected_cited:              {det['in_corpus']['any_expected_cited']}")
    print(f"    citation_recall (mean):          {det['in_corpus']['citation_recall_mean']}")
    print(f"    citation_precision (mean):       {det['in_corpus']['citation_precision_mean']}")
    print(f"    citation_grounding_failed:       {det['in_corpus']['citation_grounding_failed_count']}")
    print()
    print(f"  out-of-corpus (n={det['ooc']['n']}):")
    print(f"    refusal_correctness (overall):   {det['ooc']['refusal_correctness_overall']}")
    for p, v in det["ooc"]["by_path"].items():
        print(f"      {p}: {v}")
    print()

    op = summary["operational"]
    print("OPERATIONAL")
    print(f"  latency p50:                       {op['latency_p50_seconds']}s")
    print(f"  latency p95:                       {op['latency_p95_seconds']}s")
    print(f"  refusal_path_distribution:")
    for path, count in op["refusal_path_distribution"].items():
        print(f"    {path}: {count}")
    print()

    print("PER-QUERY SUMMARY")
    for t in transcripts:
        s = t["scores"]
        passed = s.get("passed")
        mark = "✓" if passed else "✗"
        if t.get("error"):
            print(f"  {mark} {t['id']:25} ERROR  {t['error']}")
            continue
        if t["category"] == "in_corpus":
            outcome = s.get("outcome", "?")
            cited = s.get("cited_section_refs", [])
            expected = s.get("expected_citations", [])
            recall = s.get("citation_recall")
            recall_str = f"recall={recall:.2f}" if recall is not None else "recall=n/a"
            cited_str = ",".join(cited) if cited else "—"
            print(
                f"  {mark} {t['id']:25} {outcome:8} "
                f"cite=[{cited_str}] expected=[{','.join(expected)}] {recall_str}"
            )
        else:
            outcome = s.get("outcome", "?")
            actual_r = s.get("actual_refusal_reason") or "—"
            expected_r = s.get("expected_refusal_reason") or "—"
            top = s.get("top_rerank_score_at_refusal")
            top_str = f"top_rerank={top:.3f}" if isinstance(top, (int, float)) else "top_rerank=n/a"
            print(
                f"  {mark} {t['id']:25} {outcome:8} "
                f"reason={actual_r} expected={expected_r} {top_str}"
            )

    print()
    print("HAND-GRADING")
    print(f"  {summary['hand_grading']['instructions']}")
    print(line)


# ---------------------------------------------------------------------------
# Config snapshot for run-header reproducibility
# ---------------------------------------------------------------------------


def _config_snapshot() -> dict[str, Any]:
    """Read pinned model + retrieval params for the run header. The snapshot
    travels into the summary JSON so any reviewer can reproduce the exact
    pipeline configuration used."""
    snap: dict[str, Any] = {}
    if MODELS_PATH.exists():
        models = _load_yaml(MODELS_PATH) or {}
        # Best-effort flatten; field names depend on user's models.yml shape
        for k, v in models.items():
            if isinstance(v, dict):
                # e.g. anthropic: {model: claude-sonnet-4-6, ...}
                snap[k] = v.get("model") or next(iter(v.values()), None)
            else:
                snap[k] = v
    if RETRIEVAL_PATH.exists():
        retr = _load_yaml(RETRIEVAL_PATH) or {}
        hybrid = retr.get("hybrid", {})
        reranker = retr.get("reranker", {})
        refusal = retr.get("refusal", {})
        snap["vector_top_k"] = hybrid.get("vector_top_k")
        snap["bm25_top_k"] = hybrid.get("bm25_top_k")
        snap["rrf_k_constant"] = hybrid.get("rrf_k_constant")
        snap["return_top_k"] = reranker.get("return_top_k")
        snap["threshold"] = refusal.get("rerank_score_threshold")
    return snap


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="regulated-rag v0.1 eval harness")
    ap.add_argument(
        "--filter",
        default=None,
        help="Substring filter on query id; runs only matching queries",
    )
    ap.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for runs/baseline-v0.1.{json,jsonl}",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate eval YAML and print query list; do not run pipeline",
    )
    args = ap.parse_args()

    queries = _load_eval_set(EVAL_PATH)
    if args.filter:
        queries = [q for q in queries if args.filter in q["id"]]
        if not queries:
            print(f"no queries matched filter {args.filter!r}", file=sys.stderr)
            return 2

    if args.dry_run:
        print(f"Loaded {len(queries)} queries from {EVAL_PATH}")
        for q in queries:
            print(f"  {q['id']:25} [{q['category']}]  {q['query']}")
        return 0

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "baseline-v0.1.jsonl"
    json_path = out_dir / "baseline-v0.1.json"

    log.info("running %d queries; output to %s", len(queries), out_dir)
    transcripts: list[dict] = []
    with jsonl_path.open("w", encoding="utf-8") as f:
        for q in queries:
            t = _run_one(q)
            transcripts.append(t)
            f.write(json.dumps(t, default=str, ensure_ascii=False) + "\n")

    config_snap = _config_snapshot()
    summary = _aggregate(transcripts)
    summary["ran_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary["config"] = config_snap
    summary["eval_set_path"] = str(EVAL_PATH.relative_to(REPO_ROOT))
    summary["transcripts_path"] = str(jsonl_path.relative_to(REPO_ROOT))

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str, ensure_ascii=False)

    _print_report(transcripts, summary, config_snap)

    # Exit code reflects in-corpus pass rate at the headline level. Doesn't
    # gate on hand-graded metrics (they're not yet computed) — only on the
    # deterministic any_expected_cited and refusal_correctness signals.
    ic = summary["deterministic"]["in_corpus"]
    ooc = summary["deterministic"]["ooc"]
    ic_passed = ic["any_expected_cited"]
    ooc_passed = ooc["refusal_correctness_overall"]
    print(f"\nheadline: in_corpus any_expected_cited={ic_passed}  ooc refusal_correctness={ooc_passed}")
    print(f"transcripts: {jsonl_path}")
    print(f"summary:     {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
