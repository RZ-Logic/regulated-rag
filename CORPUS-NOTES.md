# CORPUS-NOTES.md

Provenance and chunking decisions for the regulated-rag v0.1 corpus.
This document is the audit trail for *what is in the index and how it got
there*. If the eval harness flags a quality regression, this is the first
file to consult — most regressions trace back to corpus or chunking
decisions, not retrieval or generation.

---

## Corpus contents (v0.1)

| Source | Sections | Chunks | Date ingested | Provenance |
|---|---|---|---|---|
| FDCPA | 17 sections (§§ 802–818) | 120 | May 4, 2026 | Cornell LII |
| California EWA | — | — | _deferred to v0.2_ | _deferred to v0.2_ |

### California EWA: deferred to v0.2

CONTEXT.md originally scoped v0.1 as FDCPA + California EWA. The deferral was a deliberate scope cut, not a missed item: ship FDCPA clean against the architectural goal (citation grounding + refusal-on-low-confidence as enforcement boundaries) before introducing a second corpus. A two-source v0.1 would have entangled corpus expansion with retrieval-quality measurement; the architectural argument the artifact is built around stands or falls on a single corpus.

What this means concretely:

- **The pre-generation refusal layer treats California EWA as out-of-corpus** for v0.1. A query that names "California EWA" or "Earned Wage Access" by string is refused with `NAMED_REGULATION_NOT_IN_CORPUS` before the LLM is called. (See `src/regulated_rag/generation.py`'s `OUT_OF_CORPUS_REGULATIONS` list.) When the v0.2 California EWA ingest lands, those entries leave the list; the named-regulation check is "things explicitly NOT in corpus," a negative declaration of scope that updates with corpus contents.
- **The eval set in v0.1 contains FDCPA queries only.** No California EWA placeholder questions; quality metrics measure retrieval and grounding behavior on a single, fully-ingested source.
- **Schema and code paths are corpus-aware throughout.** `source` is a top-level column on `chunks`; the BM25 cache is keyed by source; the retrieval functions accept a `source` parameter. Adding California EWA in v0.2 is a new ingest run plus a new entry in this table — no schema migration, no re-architecture.

---

## FDCPA: source and provenance

**Where the text comes from**: [Cornell Legal Information Institute](https://www.law.cornell.edu/uscode/text/15) — pages under `https://www.law.cornell.edu/uscode/text/15/1692*`.

**Why Cornell LII**: clean HTML, consistent structure across sections, no
PDF parsing tax, freely accessible without authentication. The trade-off is
that Cornell LII is a *secondary* source — they transcribe from the
official U.S. Code and add light editorial annotation (definition links,
footnote markers, "prev/next" navigation). The transcription is reliable,
but it is not the canonical text.

**Canonical source acknowledgment**: the canonical FDCPA text is
[15 U.S.C. §§ 1692–1692p](https://uscode.house.gov/) maintained by the
Office of the Law Revision Counsel of the U.S. House of Representatives,
available as XML. v0.2 will switch to ingesting directly from the canonical
XML so that every chunk traces to a verifiable government-published source.
For v0.1, Cornell LII is the working source and the spot-check below is the
verification step.

**Amendment status**: the FDCPA was last meaningfully amended by
the Consumer Financial Protection Act of 2010 (Title X of Dodd-Frank,
P.L. 111–203), which transferred enforcement authority to the CFPB and
added § 818 (15 U.S.C. § 1692p). Cornell LII reflects current law; the
ingest run records the page's "How current is this?" stamp at fetch time
(visible at the bottom of every Cornell LII section page) so downstream
readers can verify currency.

**Spot-check before declaring corpus ready**: diff at least one section
(recommend § 806 / 15 U.S.C. § 1692d, the harassment section, because it
is short and has a flat enumeration that's easy to compare visually)
against the canonical XML at uscode.house.gov. Confirm subsection text
matches verbatim (allowing for whitespace and the absence of Cornell's
inline definition links).

---

## Chunking decisions

### Granularity: hierarchical, not uniform

The FDCPA does not have uniform internal structure. § 1692d (Harassment)
is a flat list of six prohibited practices. § 1692c (Communication) has
two-level nesting (e.g., (a)(1), (a)(2)). § 1692a is a definitions list
where each defined term is its own semantic unit. Forcing a single grain
on this would degrade retrieval quality.

The chunker emits:

- **One chunk per leaf enumerated unit**. Example: § 806(5) is one chunk;
  § 805(a)(1) is one chunk. These are the units that lawyers cite, that
  cases construe, and that retrieval queries most often want.
- **One chunk per *framing clause*** — the operative chapeau text that
  appears between an enumeration marker and its first child marker. The
  "A debt collector may not engage in any conduct..." opener of § 806 is
  itself substantive law and is retrievable as `§ 806` with role
  `framing_clause`. Without this, a query about "what does FDCPA say
  generally about harassment" would only retrieve the enumerated examples
  and miss the operative prohibition.
- **One chunk per standalone section** when the section has no enumeration
  (e.g., short sections like § 810 / Multiple debts).
- **One chunk per definition** in § 803, with role `definition`.

### Embedding text composition: structural prefix, not Contextual Retrieval

Chunks are embedded with a *structural prefix* prepended to the chunk_text:

> `FDCPA § 806 (Harassment or abuse), subsection (5): {chunk_text}`

This is **not** [Anthropic's Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval),
which uses an LLM to generate per-chunk context summaries. The structural
prefix is metadata-derived and costs nothing; Contextual Retrieval costs
one LLM call per chunk and is deferred to v0.2 as a measured comparison.

The prefix is composed at *embed time* and not persisted to the database.
The stored `chunk_text` is the clean substantive text only, used for
citation display in retrieval responses. If the prefix format changes,
re-embedding regenerates inputs without any data drift.

### Schema mapping

Top-level columns (the hot query path):
- `source` = `'fdcpa'`
- `section_ref` = canonical human-readable citation, e.g., `'§ 806(5)'`
  (matches the format eval queries expect for citation grounding)
- `chunk_text` = clean substantive text
- `embedding` = 1024-dim vector (Voyage `voyage-3-large`)

JSONB `metadata` (per-chunk specifics):
- `uscode_citation` — e.g., `'15 U.S.C. § 1692d(5)'`
- `fdcpa_section` — the FDCPA § number as string, e.g., `'806'`
- `fdcpa_subsection_path` — list, e.g., `['a', '1']` for § 805(a)(1)
- `section_title` — e.g., `'Harassment or abuse'`
- `chunk_role` — one of `framing_clause`, `enumerated_item`, `standalone_section`, `definition`
- `parent_ref` — section_ref of the parent chunk (for context expansion in
  v0.2). `None` for top-level chunks. Stable across re-ingests because it's
  text, not auto-increment id.
- `cross_references` — list of FDCPA § numbers cited in chunk_text, e.g.,
  `['804']` for § 806(6) which references § 1692b.

Constants pulled OUT of per-chunk metadata and into this document
(provenance applies to the ingest run, not per chunk):
- Source URL pattern: `https://www.law.cornell.edu/uscode/text/15/{slug}`
- Canonical source: `uscode.house.gov` (deferred to v0.2)
- Downloaded date: filled at ingest run time (see ingest log)

### What BM25 indexes (and why not more)

The BM25 retrieval path indexes `section_ref + " " + chunk_text` per chunk —
not the U.S.C. citation, not the section title, not the cross-references.
The decision was tested empirically in hour 6 against a U.S.C.-notation query
("What does § 1692c say about communication with consumers?") that was
predicted to fail BM25 (BM25 sees "§ 805", not "§ 1692c"; the U.S.C. citation
lives in `metadata.uscode_citation`, which BM25 doesn't see). The query did
not fail — Voyage handled the citation-form mapping semantically, and
incidental cross-references in chunk text gave BM25 partial hooks (statute
prose like "section 1692b" appears in adjacent chunks).

Concatenating `metadata.uscode_citation` into the BM25 document was the
prepared one-line fix; it's deferred to v0.2 because the empirical case for
it isn't there at v0.1 corpus scale and at FDCPA's single citation system.
v0.2 reconsiders when the corpus expands to a regulation with a different
citation system (Regulation F is CFR-numbered, California EWA uses state
statute numbering).

The principle: structural metadata enters the BM25 view only when measurement
shows the dense path can't cover it. Adding metadata fields to the BM25 doc
is cheap; *defensible* additions require evidence.

---

## Known v0.1 limitations

These are documented here rather than fixed in v0.1 because they don't
block the v0.1 quality bar (citation grounding + refusal + smoke
retrieval) and the fix-or-defer call belongs to the eval results, not to
my pre-eval intuition.

1. **Inline subsection headings live inside chunk_text.** Cornell LII
   bundles the heading for top-level subsections (e.g., "Communication
   with the consumer generally" for § 805(a)) into the same paragraph as
   the chapeau. The parser captures both as the framing-clause chunk_text,
   which means the heading appears as a sentence-fragment prefix in the
   retrieved text. Reads slightly oddly but improves recall (the heading
   is meaningful semantic context). Not separating into a dedicated
   metadata field for v0.1.

2. **Cornell LII inline link/definition wrappers can leave whitespace
   artifacts.** Words like "debt" and "consumer" are wrapped in definition
   links; when text is extracted, the trailing punctuation can end up
   space-separated (e.g., `"the debt ."` instead of `"the debt."`). Cosmetic
   — does not affect retrieval quality.

3. **No Contextual Retrieval and no LLM-generated chunk summaries.** v0.1
   embedding inputs are structural-prefix only. v0.2 will add Contextual
   Retrieval and report side-by-side recall@k vs the v0.1 baseline.

4. **BM25 index is in-memory, not Postgres-backed.** v0.1 ships hybrid
   retrieval (vector + BM25 → RRF → cross-encoder rerank) using the
   `rank_bm25` Python package, with the corpus loaded into a module-level
   cache keyed by source. Acceptable at 120 chunks; doesn't scale past a
   few thousand. v0.2 moves BM25 to a Postgres `to_tsvector` + GIN-index
   path, which keeps the corpus on disk and survives process restart.

5. **No per-section "amendment as of" stamp on individual chunks.** The
   amendment status is a corpus-level fact (this CORPUS-NOTES.md) rather
   than a per-chunk one. If a section gets amended between ingest runs,
   the right move is full re-ingest, not per-chunk patching.

---

## Re-ingest playbook

When (not if) the corpus needs to be rebuilt:

```bash
# Dry-run — fetch + chunk only, see what would land in the index.
python -m regulated_rag.ingest_fdcpa --dry-run

# Live run, replacing existing fdcpa rows.
python -m regulated_rag.ingest_fdcpa --force

# Verify end-to-end retrieval works.
python scripts/smoke_retrieval.py
```

Other sources (e.g., `ca_ewa` in v0.2) are never touched — re-ingest of
FDCPA only deletes/replaces `source='fdcpa'`.

---

_Maintained as part of the regulated-rag corpus engineering record. If
you change chunking, embedding, or source decisions, update this file in
the same PR._
