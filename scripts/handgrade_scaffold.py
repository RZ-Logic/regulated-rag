"""
Hand-grading scaffold for regulated-rag v0.1 baseline run.

Reads runs/baseline-v0.1.jsonl, fetches the cited and retrieved chunk text
from the corpus, and produces two outputs:

    runs/baseline-v0.1-handgrading.md     side-by-side reading view
                                          (claim text + cited chunk text)
    runs/baseline-v0.1-handgrading.json   empty grading skeleton — fill in
                                          faithful / answer_relevant /
                                          classification fields

Workflow:
  1. python scripts/handgrade_scaffold.py
  2. Read the .md top-to-bottom; mentally grade each claim
  3. Edit the .json filling in:
       - "faithful": true/false        per claim
       - "answer_relevant": true/false per claim
       - "classification": one of      per extra citation
           "hierarchical"  (parent/child of expected — legitimate)
           "contextual"    (Congressional intent / definitional support)
           "off_topic"     (genuine over-citation worth flagging)
       - "notes":        optional free text
       - "graded_at":    timestamp at top
       - "grader":       your name at top
  4. The .json feeds the README's "What works / what doesn't" section.

Estimated effort: ~10–15 min for ~30 claims (vs ~20 min reading raw JSONL).

This script is one-time scaffolding; not part of the production retrieval
or generation path. Lives in scripts/ alongside the eval harness.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Match the eval-harness UTF-8 posture
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from regulated_rag.db import connect, get_chunks_by_ids  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
JSONL_PATH = REPO_ROOT / "runs" / "baseline-v0.1.jsonl"
MD_OUT = REPO_ROOT / "runs" / "baseline-v0.1-handgrading.md"
JSON_OUT = REPO_ROOT / "runs" / "baseline-v0.1-handgrading.json"


def _load_transcripts() -> list[dict]:
    if not JSONL_PATH.exists():
        sys.exit(f"missing transcript: {JSONL_PATH}")
    with JSONL_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _collect_chunk_ids(transcripts: list[dict]) -> set[int]:
    """All chunk_ids that appear anywhere — cited or retrieved — for the
    in-corpus answered queries. We hydrate everything at once to minimize
    DB round-trips."""
    ids: set[int] = set()
    for t in transcripts:
        if t["category"] != "in_corpus":
            continue
        if t.get("error"):
            continue
        result = t.get("result") or {}
        if not result.get("answered"):
            continue
        for c in t.get("retrieved_top5", []):
            if c.get("chunk_id") is not None:
                ids.add(int(c["chunk_id"]))
        for claim in result.get("claims", []):
            for cid in claim.get("chunk_ids", []) or []:
                ids.add(int(cid))
    return ids


def _fetch_chunk_text_map(chunk_ids: set[int]) -> dict[int, dict]:
    """chunk_id -> {section_ref, chunk_text, ...} from Postgres."""
    if not chunk_ids:
        return {}
    with connect() as conn:
        rows = get_chunks_by_ids(conn, sorted(chunk_ids))
    return {r["id"]: r for r in rows}


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _md_blockquote(text: str) -> str:
    """Render text as a Markdown blockquote, preserving paragraph breaks."""
    if not text:
        return "> _(empty)_"
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(f"> {line}" if line else ">" for line in lines)


def _render_md(transcripts: list[dict], chunk_map: dict[int, dict]) -> str:
    out: list[str] = []
    out.append("# regulated-rag v0.1 — hand-grading template (run 1)\n")
    out.append(
        "Side-by-side view of each in-corpus query's claims and the cited chunk text. "
        "Mark grades in `runs/baseline-v0.1-handgrading.json`. This file is the reading view; "
        "the JSON is the gradesheet.\n"
    )
    out.append(
        "**For each claim:** does the claim follow from the cited chunk's text "
        "(faithfulness)? does it address the question (answer relevance)?\n"
    )
    out.append(
        "**For each 'extra' citation** (cited but not in expected): hierarchical, "
        "contextual, or off-topic?\n\n---\n"
    )

    in_corpus = [
        t
        for t in transcripts
        if t["category"] == "in_corpus" and not t.get("error")
    ]

    for t in in_corpus:
        qid = t["id"]
        query = t["query"]
        scores = t.get("scores", {})
        result = t.get("result") or {}
        expected_cites = set(scores.get("expected_citations", []) or [])
        cited_refs = scores.get("cited_section_refs", []) or []
        recall = scores.get("citation_recall")
        precision = scores.get("citation_precision")

        out.append(f"## {qid}")
        out.append(f"**Query:** {query}\n")
        out.append(
            f"**Expected:** `{', '.join(sorted(expected_cites)) or '(none)'}`  "
            f"**Cited:** `{', '.join(cited_refs) or '(none)'}`  "
            f"**Recall:** {recall if recall is None else f'{recall:.2f}'}  "
            f"**Precision:** {precision if precision is None else f'{precision:.2f}'}\n"
        )

        # Retrieved-top-5 quick reference
        out.append("**Retrieved top-5:**\n")
        out.append("| rank | chunk_id | section_ref | rerank |")
        out.append("|---:|---:|:---|---:|")
        for i, c in enumerate(t.get("retrieved_top5", []), start=1):
            rs = c.get("rerank_score")
            rs_str = f"{rs:.3f}" if isinstance(rs, (int, float)) else "—"
            out.append(
                f"| {i} | {c.get('chunk_id')} | "
                f"`{c.get('section_ref')}` | {rs_str} |"
            )
        out.append("")

        # Claims with cited chunk text
        out.append("### Claims")
        for i, claim in enumerate(result.get("claims", []), start=1):
            claim_text = claim.get("text", "")
            cited_ids = claim.get("chunk_ids", []) or []
            cited_for_claim = []
            for cid in cited_ids:
                ck = chunk_map.get(int(cid))
                if ck:
                    cited_for_claim.append(
                        f"`{ck['section_ref']}` (chunk_id {cid})"
                    )
                else:
                    cited_for_claim.append(f"chunk_id {cid} (not found)")

            out.append(f"#### Claim {i}")
            out.append(f"_Cites:_ {', '.join(cited_for_claim) or '(none)'}\n")
            out.append("**Claim text:**")
            out.append(_md_blockquote(claim_text))
            out.append("")
            out.append("**Cited chunk text:**")
            for cid in cited_ids:
                ck = chunk_map.get(int(cid))
                if not ck:
                    out.append(f"> _(chunk_id {cid} not found in corpus)_")
                    out.append("")
                    continue
                out.append(f"_{ck['section_ref']}_ (chunk_id {cid}):")
                out.append(_md_blockquote(ck["chunk_text"]))
                out.append("")
            out.append(
                "→ _grade in JSON: `faithful` (true/false), "
                "`answer_relevant` (true/false)_\n"
            )

        # Extra citations: cited but not in expected set
        cited_set = set(cited_refs)
        extras = sorted(cited_set - expected_cites)
        if extras:
            out.append("### Extra citations (cited but not in expected)")
            out.append("Classify each below in the JSON's `extra_citations` array.\n")
            # Map each extra section_ref back to the chunk_id(s) cited
            ref_to_ids: dict[str, list[int]] = {}
            for claim in result.get("claims", []):
                for cid in claim.get("chunk_ids", []) or []:
                    ck = chunk_map.get(int(cid))
                    if ck and ck["section_ref"] in extras:
                        ref_to_ids.setdefault(ck["section_ref"], []).append(int(cid))
            for ref in extras:
                ids = sorted(set(ref_to_ids.get(ref, [])))
                out.append(f"- **`{ref}`** (chunk_id(s): {ids or '—'}):")
                # Show the chunk text once for context
                if ids:
                    ck = chunk_map.get(ids[0])
                    if ck:
                        out.append(_md_blockquote(ck["chunk_text"]))
                out.append(
                    "  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_\n"
                )

        out.append("---\n")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# JSON skeleton
# ---------------------------------------------------------------------------


def _render_json_skeleton(transcripts: list[dict], chunk_map: dict[int, dict]) -> dict:
    skel: dict = {
        "version": "v0.1.0-handgrading-run1",
        "graded_at": None,
        "grader": None,
        "source_transcripts": str(JSONL_PATH.relative_to(REPO_ROOT)),
        "instructions": (
            "Fill in faithful (bool), answer_relevant (bool), and classification "
            "(one of: hierarchical | contextual | off_topic). Set graded_at to ISO "
            "timestamp and grader to your name when done. The README pulls the "
            "aggregate from this file."
        ),
        "queries": [],
    }

    for t in transcripts:
        if t["category"] != "in_corpus" or t.get("error"):
            continue
        result = t.get("result") or {}
        if not result.get("answered"):
            continue

        scores = t.get("scores", {})
        expected_cites = set(scores.get("expected_citations", []) or [])
        cited_refs = scores.get("cited_section_refs", []) or []

        # Per-claim entries
        claim_entries = []
        for i, claim in enumerate(result.get("claims", [])):
            cited_ids = claim.get("chunk_ids", []) or []
            cited_section_refs = []
            for cid in cited_ids:
                ck = chunk_map.get(int(cid))
                if ck:
                    cited_section_refs.append(ck["section_ref"])
            claim_entries.append({
                "claim_index": i,
                "claim_text": claim.get("text", ""),
                "cited_chunk_ids": list(cited_ids),
                "cited_section_refs": cited_section_refs,
                "faithful": None,
                "answer_relevant": None,
                "notes": "",
            })

        # Extra citations (cited but not expected) for classification
        extras_set = set(cited_refs) - expected_cites
        extra_entries = []
        # Map ref -> chunk_ids
        ref_to_ids: dict[str, list[int]] = {}
        for claim in result.get("claims", []):
            for cid in claim.get("chunk_ids", []) or []:
                ck = chunk_map.get(int(cid))
                if ck and ck["section_ref"] in extras_set:
                    ref_to_ids.setdefault(ck["section_ref"], []).append(int(cid))
        for ref in sorted(extras_set):
            extra_entries.append({
                "section_ref": ref,
                "chunk_ids": sorted(set(ref_to_ids.get(ref, []))),
                "classification": None,  # hierarchical | contextual | off_topic
                "notes": "",
            })

        skel["queries"].append({
            "id": t["id"],
            "query": t["query"],
            "expected_citations": sorted(expected_cites),
            "cited_section_refs": cited_refs,
            "claims": claim_entries,
            "extra_citations": extra_entries,
            "overall_quality": None,  # good | ok | poor — optional global judgment
            "notes": "",
        })

    return skel


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    transcripts = _load_transcripts()
    print(f"loaded {len(transcripts)} transcripts from {JSONL_PATH}", flush=True)

    chunk_ids = _collect_chunk_ids(transcripts)
    print(f"unique chunk_ids to hydrate: {len(chunk_ids)}", flush=True)

    chunk_map = _fetch_chunk_text_map(chunk_ids)
    print(f"fetched {len(chunk_map)} chunks from corpus", flush=True)

    md = _render_md(transcripts, chunk_map)
    json_skel = _render_json_skeleton(transcripts, chunk_map)

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text(md, encoding="utf-8")
    with JSON_OUT.open("w", encoding="utf-8") as f:
        json.dump(json_skel, f, indent=2, ensure_ascii=False)

    n_claims = sum(len(q["claims"]) for q in json_skel["queries"])
    n_extras = sum(len(q["extra_citations"]) for q in json_skel["queries"])
    print()
    print(f"wrote {MD_OUT}  ({len(md):,} chars)")
    print(f"wrote {JSON_OUT}  ({len(json_skel['queries'])} queries, "
          f"{n_claims} claims, {n_extras} extra-citation classifications)")
    print()
    print("workflow:")
    print(f"  1. read    {MD_OUT.relative_to(REPO_ROOT)}")
    print(f"  2. fill    {JSON_OUT.relative_to(REPO_ROOT)}  (faithful/answer_relevant/classification)")
    print(f"  3. set     graded_at + grader at top of JSON when done")
    print(f"  4. README  pulls aggregate from filled JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
