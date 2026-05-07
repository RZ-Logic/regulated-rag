"""
Hour 7 smoke for the full retrieval + generation pipeline.

Four queries, four architectural paths exercised:

  1. PASS: hour-5 canonical query
     → retrieval succeeds, generator answers, citations validate.
     This is the "happy path" that proves the pipeline produces a
     citation-grounded answer end-to-end.

  2. RETRIEVAL-LAYER REFUSAL: clearly off-corpus query
     → refused at the hour-5 reranker threshold (top score < 0.30).
     The LLM is never called. Saves a request and the spend that goes
     with it; refusal is the audit-correct output.

  3. PRE-GEN REFUSAL: adjacent-domain query (the hour-6 finding made
     architecturally enforceable in hour 7)
     → refused before LLM call by the named-regulation regex.
     Top reranker score IS above threshold here -- retrieval returns
     plausible FDCPA chunks for "debt collector calls" -- which is
     exactly why this check has to live OUTSIDE the threshold.

  4. POST-GEN VALIDATION (deferred to eval set):
     citation_grounding_failed and generator_declined are validated by
     the eval harness in hour 8, not the smoke. Smoke covers only the
     paths that one canonical query each can exercise reliably.

Read the output top-to-bottom. Each block prints the deterministic check
that fired and why. The architectural argument -- "stochastic stage
bounded by deterministic checks on both sides" -- should be visually
obvious from the labelled refusal_reason on each refused result.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # entry-point owns dotenv per hour-5 decision

from regulated_rag.generation import (
    GenerationResult,
    RefusalReason,
    generate,
    result_to_dict,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("smoke-h7")


SMOKE_QUERIES: list[tuple[str, str, str]] = [
    # (label, query, expected_path)
    (
        "pass-hour5-canonical",
        "Can a debt collector call me before 8am or after 9pm?",
        "answered",
    ),
    (
        "retrieval-refusal-traffic",
        "What is the speed limit in California highways?",
        f"refused:{RefusalReason.LOW_RETRIEVAL_CONFIDENCE.value}",
    ),
    (
        "pregen-refusal-regf",
        "What does Regulation F say about debt collector calls?",
        f"refused:{RefusalReason.NAMED_REGULATION_NOT_IN_CORPUS.value}",
    ),
]


def print_result(label: str, expected_path: str, result: GenerationResult) -> bool:
    """Returns True if the actual path matches the expected path."""
    print()
    print("=" * 88)
    print(f"[{label}]")
    print(f"query:    {result.query}")
    print(f"expected: {expected_path}")

    if result.refused:
        actual_path = f"refused:{result.refusal_reason.value if result.refusal_reason else 'unknown'}"
        print(f"actual:   {actual_path}")
        print(f"reason:   {result.refusal_message}")
        if result.refusal_detail:
            print(f"detail:   {result.refusal_detail}")
        if result.detected_regulation:
            print(f"detected: {result.detected_regulation}")
        if result.retrieved_top_rerank_score is not None:
            print(f"top_rerank_at_refusal: {result.retrieved_top_rerank_score:.4f}")
        if result.model:
            print(f"model:    {result.model}  request_id={result.request_id}")
    else:
        actual_path = "answered"
        print(f"actual:   {actual_path}")
        print(f"model:    {result.model}  request_id={result.request_id}")
        print(f"top_rerank_at_answer: {result.retrieved_top_rerank_score:.4f}")
        print(f"retrieved_chunk_ids:  {result.retrieved_chunk_ids}")
        print()
        print(f"  {len(result.claims)} claims:")
        for i, c in enumerate(result.claims, 1):
            print(f"  [{i}] cites {c.chunk_ids}")
            # wrap claim text for readability
            words = c.text.split()
            line = "      "
            for w in words:
                if len(line) + len(w) + 1 > 84:
                    print(line)
                    line = "      " + w
                else:
                    line = line + (" " if line.strip() else "") + w
            if line.strip():
                print(line)

    print(f"elapsed:  {result.elapsed_seconds}s")
    matched = (actual_path == expected_path)
    verdict = "✓ matched expected path" if matched else "✗ MISMATCH"
    print(f"verdict:  {verdict}")
    return matched


def main() -> int:
    out_dir = Path("runs")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "smoke-h7.jsonl"

    print(f"Running {len(SMOKE_QUERIES)} hour-7 smoke queries...")
    print(f"Results will be archived to: {out_path}")

    matches = 0
    with out_path.open("w") as f:
        for label, query, expected_path in SMOKE_QUERIES:
            log.info("smoke %s: %s", label, query)
            try:
                result = generate(query)
            except Exception as exc:
                log.exception("smoke %s raised", label)
                print(f"\n[{label}] ERROR: {exc!r}")
                f.write(json.dumps({"label": label, "error": repr(exc)}) + "\n")
                continue
            ok = print_result(label, expected_path, result)
            if ok:
                matches += 1
            f.write(json.dumps({
                "label": label,
                "expected_path": expected_path,
                "result": result_to_dict(result),
            }, default=str) + "\n")

    print()
    print("#" * 88)
    print(f"# SMOKE SUMMARY: {matches}/{len(SMOKE_QUERIES)} paths matched")
    print("#" * 88)
    print(f"\nArchived to {out_path}")
    return 0 if matches == len(SMOKE_QUERIES) else 1


if __name__ == "__main__":
    sys.exit(main())
