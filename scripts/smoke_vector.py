"""
Hour 3-4 smoke retrieval test.

Embeds a known-answer query against the freshly-ingested FDCPA corpus and
verifies that § 805(a)(1) — the operative '8am rule' subsection — appears in
the top-5 cosine-similarity results. Exits 0 on PASS, 1 on FAIL.

This is a *smoke test*, not a quality eval. It tells us the pipeline (chunk
-> embed -> store -> retrieve) is end-to-end functional. Real eval comes in
hour 8-9 with the eval harness from finagent-evals.
"""

from __future__ import annotations

import logging
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from regulated_rag.db import connect, cosine_search
from regulated_rag.embedder import embed_query


SOURCE = "fdcpa"
QUERY = "Can a debt collector call me before 8am or after 9pm?"
EXPECTED_SECTION_REF = "§ 805(a)(1)"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("smoke_retrieval")

    log.info("Query: %r", QUERY)
    log.info("Expected to find %s in top-5.", EXPECTED_SECTION_REF)

    log.info("Embedding query (input_type='query')...")
    qvec = embed_query(QUERY)
    log.info("Query embedding: dim=%d, first 4 dims=%s",
             len(qvec), [round(x, 4) for x in qvec[:4]])

    with connect() as conn:
        results = cosine_search(conn, qvec, source=SOURCE, limit=5)

    log.info("Top-5 results:")
    print()
    for i, r in enumerate(results, 1):
        snippet = r["chunk_text"][:140].replace("\n", " ")
        more = "..." if len(r["chunk_text"]) > 140 else ""
        print(f"  {i}. {r['section_ref']:14s} sim={r['similarity']:.4f}")
        print(f"      {snippet}{more}")
        print()

    found = any(r["section_ref"] == EXPECTED_SECTION_REF for r in results)
    rank = next(
        (i for i, r in enumerate(results, 1)
         if r["section_ref"] == EXPECTED_SECTION_REF),
        None,
    )

    if found:
        log.info("PASS: %s found at rank %d.", EXPECTED_SECTION_REF, rank)
        return 0
    else:
        log.error("FAIL: %s not in top-5.", EXPECTED_SECTION_REF)
        log.error("Top-5 returned: %s",
                  [r["section_ref"] for r in results])
        return 1


if __name__ == "__main__":
    sys.exit(main())
