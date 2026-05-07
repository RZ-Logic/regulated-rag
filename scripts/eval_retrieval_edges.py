"""
Hour 6 hardening harness for the hybrid retrieval pipeline.

Methodology
-----------
This is not a pass/fail test. It is a probe. Each query is paired with a
*pre-registered prediction* of how the pipeline should behave; the harness
prints predicted vs actual side by side so surprises are visible. Read the
output the way you'd read a small experiment's results, not a unit test
report.

Categories
----------
1. Citation-string queries (FDCPA notation): BM25 should boost hits via
   literal section_ref match, even when the vector embedder is fuzzy on
   symbolic tokens like '§'.
2. Citation-string queries (U.S.C. notation): the failure mode under test.
   `_build_bm25_index` tokenizes `section_ref + chunk_text` only. The U.S.C.
   citation (e.g., '§ 1692c') lives in metadata.uscode_citation, which BM25
   never sees. If '§ 1692c' degrades, that's the predicted architectural
   gap — fix is one-line if confirmed.
3. Buried-answer queries: query language doesn't share keyword surface
   with the answer chunk. Tests whether vector retrieval + reranker bridge
   the semantic gap that BM25 cannot.
4. Off-corpus queries: should trip the refusal threshold from ABOVE. The
   hour-5 smoke proved ranks 2-5 sit below threshold; a true off-corpus
   query should pull rank 1 below it as well.
5. Adjacent-domain query: Regulation F is the CFPB's implementing rule for
   FDCPA. v0.2 corpus. The query is *semantically* in scope (debt collector
   calls) but the cited regulation is not in this index. The refusal
   threshold is unlikely to catch this — finding to be flagged for hour 7
   generation-layer handling.

Disagreement-consistency check
------------------------------
For each query: Jaccard(vector_top_10_ids, bm25_top_10_ids). Low Jaccard
means the two retrievers see different things and BM25 is adding info.
High Jaccard means BM25 is redundant. Hour 5 showed asymmetry on one query;
hour 6 confirms whether that's a pattern.

Output
------
Console: human-readable per-query summary.
File: `runs/edges-h6.jsonl` — one JSON line per query, machine-readable
for hour-8 eval harness ingestion.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # entry-point owns dotenv per hour-5 decision

from regulated_rag.db import connect, get_chunks_by_ids
from regulated_rag.retrieval import (
    bm25_retrieve,
    hybrid_retrieve,
    vector_retrieve,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("edges-h6")


# ---------------------------------------------------------------------------
# Pre-registered queries
# ---------------------------------------------------------------------------


@dataclass
class Probe:
    """One pre-registered query with expected behavior. The expectation is
    documented before the run; the post-run delta is what you read."""

    qid: str
    category: str
    query: str
    expect_refused: bool
    # For non-refused queries: substring match against rank-1 section_ref.
    # Empty string = "we don't have a strong prediction; just inspect."
    expect_top_section_contains: str
    # Free-text rationale; printed alongside the result for honest comparison.
    prediction_note: str


PROBES: list[Probe] = [
    # 1. Citation-string queries -- FDCPA notation
    Probe(
        qid="cite-fdcpa-bare",
        category="citation_fdcpa",
        query="§ 805",
        expect_refused=False,
        expect_top_section_contains="805",
        prediction_note=(
            "Bare citation, no English. Vector embedder will be fuzzy on "
            "symbolic tokens; BM25 should boost § 805 chunks via literal "
            "section_ref match. Strong asymmetry expected: BM25 should "
            "dominate the RRF input."
        ),
    ),
    Probe(
        qid="cite-fdcpa-context",
        category="citation_fdcpa",
        query="What does § 806 prohibit?",
        expect_refused=False,
        expect_top_section_contains="806",
        prediction_note=(
            "Citation embedded in natural-language question. Both retrievers "
            "should hit § 806; reranker should pick framing or one of (1)-(6)."
        ),
    ),
    # 2. Citation-string query -- U.S.C. notation (the predicted gap)
    Probe(
        qid="cite-uscode",
        category="citation_uscode",
        query="What does § 1692c say about communication with consumers?",
        expect_refused=False,
        expect_top_section_contains="805",  # § 1692c == FDCPA § 805
        prediction_note=(
            "PREDICTED FAILURE: section_ref is '§ 805', not '§ 1692c'. "
            "BM25 doc = 'section_ref + chunk_text'; uscode_citation lives "
            "in metadata which BM25 never sees. Cross-references in chunk "
            "text MAY help if other sections cite 1692c. Otherwise vector "
            "alone has to bridge — and embedders are notoriously fuzzy on "
            "numeric/symbolic tokens. If § 805 doesn't appear in top-3, "
            "the BM25 indexing decision is wrong: one-line fix to "
            "concatenate uscode_citation into the BM25 doc."
        ),
    ),
    # 3. Buried-answer queries -- semantic gap, vector should bridge
    Probe(
        qid="buried-work",
        category="buried_answer",
        query="Can a debt collector contact me at work?",
        expect_refused=False,
        expect_top_section_contains="805(a)(3)",
        prediction_note=(
            "Query says 'at work'; statute says 'place of employment'. "
            "Vector should bridge work→employment. BM25 will likely miss "
            "this chunk entirely. Tests the asymmetric value of dense "
            "retrieval — if vector also misses, the embedder is the "
            "weakness, not the architecture."
        ),
    ),
    Probe(
        qid="buried-neighbors",
        category="buried_answer",
        query="Can a debt collector tell my neighbors about my debt?",
        expect_refused=False,
        expect_top_section_contains="805(b)",
        prediction_note=(
            "Query says 'neighbors'; statute says 'any person other than "
            "the consumer, his attorney, a consumer reporting agency...'. "
            "Pure semantic bridge. § 804 (location info) is also in scope; "
            "either is acceptable. If § 806 (harassment) ranks first, the "
            "reranker is reading the question wrong."
        ),
    ),
    Probe(
        qid="buried-stop-calling",
        category="buried_answer",
        query="What happens if I tell the collector to stop calling me?",
        expect_refused=False,
        expect_top_section_contains="805(c)",
        prediction_note=(
            "§ 805(c) (Ceasing communication) is the answer. Some keyword "
            "overlap on 'collector' but 'stop calling' is conversational "
            "framing; statute uses 'cease further communication'. Vector "
            "bridge required."
        ),
    ),
    # 4. Off-corpus queries -- should refuse
    Probe(
        qid="off-corpus-sec",
        category="off_corpus",
        query="What are SEC disclosure requirements for IPOs?",
        expect_refused=True,
        expect_top_section_contains="",
        prediction_note=(
            "Securities law; not in corpus. Top reranker score should land "
            "below 0.30 threshold. If it doesn't, the threshold is too low "
            "OR the reranker is being misled by lexical overlap on generic "
            "terms ('requirements'). Either way, a finding."
        ),
    ),
    Probe(
        qid="off-corpus-traffic",
        category="off_corpus",
        query="What is the speed limit in California highways?",
        expect_refused=True,
        expect_top_section_contains="",
        prediction_note=(
            "Wholly off-domain; should refuse cleanly with low rerank score. "
            "If this does NOT refuse, the threshold is set too low or the "
            "reranker has serious calibration issues."
        ),
    ),
    Probe(
        qid="off-corpus-gdpr",
        category="off_corpus",
        query="What does GDPR say about a consumer's right to data deletion?",
        expect_refused=True,
        expect_top_section_contains="",
        prediction_note=(
            "Privacy/data-protection law, not debt collection. The word "
            "'consumer' overlaps with FDCPA's 'consumer'; tests whether the "
            "reranker is fooled by single-token overlap. If § 805(c) "
            "(ceasing communication) ranks high enough to clear threshold, "
            "the reranker is over-weighting 'consumer'."
        ),
    ),
    # 5. Adjacent-domain edge case
    Probe(
        qid="adjacent-regf",
        category="adjacent_domain",
        query="What does Regulation F say about debt collector calls?",
        expect_refused=True,  # what we WANT
        expect_top_section_contains="",
        prediction_note=(
            "PREDICTED ARCHITECTURAL FINDING: query is semantically in scope "
            "(debt collector calls) but cites a regulation not in this corpus "
            "(Reg F, CFPB v0.2). The reranker will likely score § 805(a)(1) "
            "or § 805(a) high because 'debt collector calls' lexically "
            "matches. The threshold-based refusal CANNOT catch this — it's "
            "a query-intent vs. corpus-source mismatch, which is a different "
            "failure mode. If this does not refuse (most likely), it's the "
            "first concrete artifact for the hour-7 generation layer to "
            "handle: the generator must either refuse on cited-source "
            "mismatch or explicitly disclose 'corpus contains FDCPA, not "
            "Reg F'."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Disagreement diagnostic (vector vs BM25 top-K Jaccard)
# ---------------------------------------------------------------------------


def disagreement_diagnostic(
    query: str,
    *,
    source: str = "fdcpa",
    k: int = 10,
) -> dict:
    """Run vector + BM25 separately at top-k and compute Jaccard. This
    re-runs the same retrievers hybrid_retrieve runs but in isolation, so
    the disagreement is observable independent of RRF/rerank smoothing."""
    with connect() as conn:
        vec = vector_retrieve(conn, query, source=source, k=k)
    bm25 = bm25_retrieve(query, source=source, k=k)

    vec_ids = {cid for cid, _ in vec}
    bm25_ids = {cid for cid, _ in bm25}
    inter = vec_ids & bm25_ids
    union = vec_ids | bm25_ids
    jaccard = (len(inter) / len(union)) if union else 0.0

    return {
        "vector_top_k_ids": [cid for cid, _ in vec],
        "bm25_top_k_ids": [cid for cid, _ in bm25],
        "intersection_size": len(inter),
        "union_size": len(union),
        "jaccard": jaccard,
    }


# ---------------------------------------------------------------------------
# Per-probe runner
# ---------------------------------------------------------------------------


def run_probe(probe: Probe) -> dict:
    """Run one probe end-to-end. Returns a dict for jsonl serialization
    plus printing."""
    t0 = time.perf_counter()
    result = hybrid_retrieve(probe.query)
    diag = disagreement_diagnostic(probe.query, k=10)
    elapsed = time.perf_counter() - t0

    chunks = [
        {
            "rank": i + 1,
            "section_ref": c.section_ref,
            "rerank_score": c.rerank_score,
            "rrf_score": c.rrf_score,
            "vector_score": c.vector_score,
            "bm25_score": c.bm25_score,
            "chunk_text_preview": c.chunk_text[:120].replace("\n", " "),
        }
        for i, c in enumerate(result.chunks)
    ]

    # Determine prediction outcome
    if probe.expect_refused:
        prediction_held = result.refused
    else:
        if result.refused:
            prediction_held = False
        elif probe.expect_top_section_contains == "":
            prediction_held = None  # no strong prediction, just inspect
        else:
            top_section = result.chunks[0].section_ref if result.chunks else ""
            prediction_held = probe.expect_top_section_contains in top_section

    return {
        "qid": probe.qid,
        "category": probe.category,
        "query": probe.query,
        "expect_refused": probe.expect_refused,
        "expect_top_section_contains": probe.expect_top_section_contains,
        "prediction_note": probe.prediction_note,
        "actual_refused": result.refused,
        "actual_refusal_reason": result.refusal_reason,
        "actual_top_rerank_score": result.top_rerank_score,
        "actual_top_section": (
            result.chunks[0].section_ref if result.chunks else None
        ),
        "prediction_held": prediction_held,
        "chunks": chunks,
        "disagreement": diag,
        "elapsed_seconds": round(elapsed, 3),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_probe_result(r: dict) -> None:
    """Human-readable per-probe block. Designed to be read top-to-bottom
    for surprises, not scanned for pass/fail."""
    print()
    print("=" * 88)
    print(f"[{r['qid']}]  category: {r['category']}")
    print(f"query:       {r['query']}")
    print(f"prediction:  refused={r['expect_refused']}  "
          f"top_contains='{r['expect_top_section_contains']}'")
    note_lines = []
    line = ""
    for word in r["prediction_note"].split():
        if len(line) + len(word) + 1 > 80:
            note_lines.append(line)
            line = "  " + word
        else:
            line = (line + " " + word) if line else "  " + word
    if line:
        note_lines.append(line)
    for ln in note_lines:
        print(ln)
    print("-" * 88)
    print(f"actual:      refused={r['actual_refused']}  "
          f"top_section={r['actual_top_section']}  "
          f"top_rerank={r['actual_top_rerank_score']}")
    if r["actual_refused"]:
        print(f"refusal_reason: {r['actual_refusal_reason']}")
    held = r["prediction_held"]
    if held is True:
        verdict = "✓ prediction held"
    elif held is False:
        verdict = "✗ prediction broken — surprise to investigate"
    else:
        verdict = "— no strong prediction; inspect chunks"
    print(f"verdict:     {verdict}")
    print(f"jaccard(vector∩bm25 @ 10): {r['disagreement']['jaccard']:.3f}  "
          f"(|∩|={r['disagreement']['intersection_size']}, "
          f"|∪|={r['disagreement']['union_size']})")

    if r["chunks"]:
        print()
        print(f"  {'rank':<5}{'section_ref':<22}"
              f"{'rerank':<10}{'rrf':<10}{'vector':<10}{'bm25':<10}")
        print("  " + "-" * 66)
        for c in r["chunks"]:
            rerank_s = f"{c['rerank_score']:.4f}" if c['rerank_score'] is not None else "—"
            rrf_s = f"{c['rrf_score']:.4f}" if c['rrf_score'] is not None else "—"
            vec_s = f"{c['vector_score']:.4f}" if c['vector_score'] is not None else "—"
            bm25_s = f"{c['bm25_score']:.4f}" if c['bm25_score'] is not None else "—"
            print(f"  {c['rank']:<5}{c['section_ref']:<22}"
                  f"{rerank_s:<10}{rrf_s:<10}{vec_s:<10}{bm25_s:<10}")


def print_summary(results: list[dict]) -> None:
    print()
    print("#" * 88)
    print("# SUMMARY")
    print("#" * 88)

    # Predictions held / broken / no-prediction counts
    held = sum(1 for r in results if r["prediction_held"] is True)
    broken = sum(1 for r in results if r["prediction_held"] is False)
    nopred = sum(1 for r in results if r["prediction_held"] is None)
    print(f"\nPredictions: {held} held, {broken} broken, {nopred} no-prediction "
          f"(of {len(results)})")

    # Per-category breakdown
    by_cat: dict[str, list[dict]] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    print("\nPer-category:")
    for cat, rs in by_cat.items():
        h = sum(1 for r in rs if r["prediction_held"] is True)
        b = sum(1 for r in rs if r["prediction_held"] is False)
        n = sum(1 for r in rs if r["prediction_held"] is None)
        print(f"  {cat:<22} {h} held / {b} broken / {n} no-pred  (n={len(rs)})")

    # Disagreement distribution
    jaccards = [r["disagreement"]["jaccard"] for r in results]
    if jaccards:
        avg = sum(jaccards) / len(jaccards)
        print(f"\nVector vs BM25 Jaccard@10 across {len(jaccards)} queries:")
        print(f"  min={min(jaccards):.3f}  avg={avg:.3f}  max={max(jaccards):.3f}")
        print(f"  per-query: " + " ".join(f"{j:.2f}" for j in jaccards))
        if avg < 0.5:
            print(
                "  → BM25 and vector consistently see different chunks. "
                "BM25 is contributing real signal; keep it."
            )
        elif avg > 0.8:
            print(
                "  → BM25 and vector consistently overlap. BM25 may be "
                "redundant; investigate."
            )
        else:
            print(
                "  → Moderate disagreement. Read individual queries for the "
                "pattern."
            )

    # Refusal correctness
    expected_refusals = [r for r in results if r["expect_refused"]]
    if expected_refusals:
        refused_correctly = sum(1 for r in expected_refusals if r["actual_refused"])
        print(f"\nRefusal correctness on expected-refusal queries: "
              f"{refused_correctly}/{len(expected_refusals)}")
        for r in expected_refusals:
            mark = "✓" if r["actual_refused"] else "✗"
            score = r["actual_top_rerank_score"]
            score_str = f"{score:.3f}" if score is not None else "n/a"
            print(f"  {mark} {r['qid']:<22} top_rerank={score_str}  "
                  f"top_section={r['actual_top_section']}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    out_dir = Path("runs")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "edges-h6.jsonl"

    print(f"Running {len(PROBES)} hour-6 edge-case probes...")
    print(f"Results will be written to: {out_path}")

    results = []
    with out_path.open("w") as f:
        for probe in PROBES:
            log.info("probe %s: %s", probe.qid, probe.query)
            try:
                r = run_probe(probe)
            except Exception as exc:
                log.exception("probe %s raised", probe.qid)
                r = {
                    "qid": probe.qid,
                    "category": probe.category,
                    "query": probe.query,
                    "error": repr(exc),
                }
            results.append(r)
            f.write(json.dumps(r, default=str) + "\n")
            print_probe_result(r) if "error" not in r else print(
                f"\n[{r['qid']}] ERROR: {r['error']}"
            )

    print_summary([r for r in results if "error" not in r])
    print(f"\nWrote {len(results)} records to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
