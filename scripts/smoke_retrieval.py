"""
Hour 5 smoke test for the hybrid retrieval pipeline.

The same query that passed the bare-vector smoke at end of hour 4 must
still rank § 805(a)(1) at rank 1 after going through
vector -> BM25 -> RRF -> rerank.

If it doesn't, the regression is in the retrieval module, not the corpus.
The hour-4 smoke (vector-only) is the control.

Hour-4 baseline for comparison:
    § 805(a)(1) at rank 1, cosine sim 0.6601, clean separation from
    rank 2 at 0.5467. Reranker score should land WELL above 0.30
    (the placeholder refusal threshold) on this query.
"""

import logging
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from regulated_rag.retrieval import hybrid_retrieve

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

QUERY = "Can a debt collector call me before 8am or after 9pm?"
EXPECTED_TOP_SECTION = "§ 805(a)(1)"


def main() -> int:
    result = hybrid_retrieve(QUERY)

    print(f"\nQuery: {QUERY}")
    print(f"Refused: {result.refused}")
    if result.refused:
        print(f"Reason: {result.refusal_reason}")
        return 1

    print(f"Top reranker score: {result.top_rerank_score:.4f}\n")
    header = f"{'rank':<5}{'section_ref':<20}{'rerank':<10}{'rrf':<10}{'vector':<10}{'bm25':<10}"
    print(header)
    print("-" * len(header))
    for i, c in enumerate(result.chunks, 1):
        rerank_s = f"{c.rerank_score:.4f}" if c.rerank_score is not None else "—"
        rrf_s = f"{c.rrf_score:.4f}" if c.rrf_score is not None else "—"
        vec_s = f"{c.vector_score:.4f}" if c.vector_score is not None else "—"
        bm25_s = f"{c.bm25_score:.4f}" if c.bm25_score is not None else "—"
        print(f"{i:<5}{c.section_ref:<20}{rerank_s:<10}{rrf_s:<10}{vec_s:<10}{bm25_s:<10}")
        # First 100 chars of the chunk so a misranked result is obvious from the text alone
        preview = c.chunk_text[:100].replace("\n", " ")
        print(f"     {preview}...")

    top = result.chunks[0]
    if top.section_ref != EXPECTED_TOP_SECTION:
        print(f"\nFAIL: expected {EXPECTED_TOP_SECTION} at rank 1, got {top.section_ref}")
        return 1

    print(f"\nPASS: {EXPECTED_TOP_SECTION} ranked first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
