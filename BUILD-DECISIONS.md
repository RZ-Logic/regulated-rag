# Build Decisions & Lessons Learned

The interesting decisions weren't the obvious ones. Five non-obvious choices and the alternatives I rejected, with empirical evidence for each.

← back to [`README.md`](./README.md)

---

## 1. Cornell LII's structural classes lie about hierarchy

The chunker took **three full rewrites** before locking. Each rewrite revealed a wrong assumption about Cornell LII's HTML.

The first parser used `<p>` tags. Cornell's body uses `<span>` and `<div>` exclusively — no `<p>` tags in the section body at all. Result: 0 chunks per section. Lesson: fetch raw HTML before building fixtures, not after.

The second parser keyed on `.paragraph` class — worked for § 1692d, failed for § 1692j and § 1692m. Cornell uses `.subsection` for letter-enumerated subsections, not `.paragraph`. Inconsistent class names for the same structural role.

The third parser added the alias and worked across all 17 sections — but § 805(a)(1) was labeled `§ 805(1)`. Cornell's `indent2` class is **visual styling, not semantic depth**: § 1692c uses `subsection.indent2` for `(a)` wrapping `paragraph.indent1` for `(a)(1)`. Higher indent class = *outer* level, not inner. Driving the citation stack from indent classes meant `(1)`'s same-level marker popped `(a)` off the stack.

The fourth parser drove the stack from **physical DOM containment** — push when entering a child node, pop when leaving. The indent class became informational, not structural. All five real-Cornell fixtures parsed correctly, including § 805(c)'s chapeau + continuation pattern, with citations matching how the statute is actually cited.

> **The principle:** Structural classes can lie about hierarchy. DOM containment doesn't. When an HTML class encodes presentation rather than semantics, the semantic walker must come from the DOM tree, not from class names.

---

## 2. The adjacent-domain finding: refusal threshold can't catch every gap

Hour 6's edge-case probe surfaced an architectural problem. Reg F is the CFPB's implementing rule for FDCPA — semantically in scope (*"debt collector calls"*), corpus-source out of scope. Retrieval pulled plausible FDCPA chunks above the 0.30 threshold because the *topic* matched.

The threshold-based refusal was designed for the case where retrieval finds nothing relevant. It cannot distinguish *"system has high-confidence retrieval against this corpus"* from *"user is asking about a different corpus that happens to overlap topically."* The same architectural problem appears in any retrieval system whose user might not know which corpus is loaded.

Two layers were considered. Lower the threshold (rejected: degrades in-corpus refusal correctness). Add a per-corpus bias term to the reranker score (rejected: entangles corpus-specific logic with general retrieval). The right factoring was a **separate deterministic check at a different stage**: a regex pre-check against the query string, before retrieval runs at all.

Hour 7 added the named-regulation pre-check. Hour 8's eval validated it: 3/3 on Reg F, GDPR, TILA queries — all refused before any embedding API call, before any reranker call, before any LLM call. CPU-cheap deterministic decisions when they can be made deterministically.

The maintenance posture is explicit: the `OUT_OF_CORPUS_REGULATIONS` list is *"things explicitly NOT in corpus"* — a negative declaration of scope that updates with corpus contents. When v0.2 lands Reg F, that entry leaves the list.

> **The principle:** Different deterministic checks at different stages do different jobs. Don't entangle corpus-source membership with retrieval quality — they're separate questions with separate failure modes. When a single check can't distinguish two failure cases, add a check at a different boundary, not a knob to the same one.

---

## 3. Refusal is a top-1 reranker check, not an aggregate

The first refusal threshold draft used mean-of-top-N reranker scores. Hour 5 smoke-tested this and it would have refused the canonical passing query.

The smoke output: query *"Can a debt collector call me before 8am or after 9pm?"* returned § 805(a)(1) at rank 1 with rerank score 0.83, but ranks 2–5 were all below 0.30 (0.23, 0.20, 0.18, 0.17). A correct retrieval has a sharp top-1 / top-2 separation. A weak retrieval has a flat distribution across ranks. Mean-of-top-N would refuse the passing query because the lower ranks dragged the aggregate below threshold.

Top-1 score is the right confidence proxy. Hour 6's edge-case probe confirmed it generalizes: true off-corpus queries pull rank 1 *down* into the same range as the unrelated lower ranks; legitimate queries have rank 1 standing well above the rest.

> **The principle:** Aggregate metrics smooth signal *and* noise. When the architectural question is *"is the top result high-confidence,"* aggregating across the top-N answers a different question. Calibrate the metric to what's being decided.

---

## 4. The named-regulation pre-check runs *before* the LLM, not after

A subtler version of #2. The pre-check could have lived inside `generate()` after retrieval, as a final guard. Architecturally that would have been wrong.

Running the pre-check before retrieval:

- **Saves API spend.** A query naming Reg F never embeds the query (Voyage call), never reranks (Cohere call), never generates (Anthropic call). At eval scale this is rounding error; at production scale it matters.
- **Makes the audit trail correct.** A `NAMED_REGULATION_NOT_IN_CORPUS` refusal logged *after* a successful retrieval invites the question *"why did you retrieve high-confidence chunks for a query you then refused?"* Running the check first means the trail says *"refused this query before any retrieval happened"* — which is what actually occurred.
- **Decouples the check from retrieval state.** The check is a property of the *query string*, not of the retrieval result. Putting it in retrieval would imply it depends on what retrieval found. It doesn't.

Hour-8 logging caught a deferred version of this issue. `ooc-004-namedreg` (Reg F query) took 16 seconds because the pre-check was inside `generate_from_retrieval()` — Cohere rerank fired and hit a 429 before the regex pre-check decided the query was OOC. The check is CPU-cheap; running it first short-circuits a wasted Voyage embed + Cohere rerank pair on every named-regulation refusal. Logged as a v0.2 task to move the pre-check to its architecturally-correct position before retrieval.

> **The principle:** Cheap deterministic checks belong as early as their dependencies allow. If the check is a property of the query string, run it on the query string — not on the retrieval result.

---

## 5. BM25 cache is module-level, keyed by source — not rebuilt per query

The first draft rebuilt the BM25 index on every retrieval call. Functionally correct, operationally wasteful: 20+ queries per eval session × ~120 chunks per source × tokenization cost = real time burned for no semantic benefit, since the corpus only changes when ingest runs.

Module-level cache, keyed by source, was the alternative. Rebuilds happen on Python process restart (acceptable for a CLI tool); v0.2's multi-corpus retrieval (FDCPA + Reg F + EWA) gets correctness for free because the cache is per-source.

The structural decision: **what BM25 indexes** is `section_ref + chunk_text`, not `chunk_text` alone. Citation-string queries (*"§ 1692c"*, *"§ 805"*) are a known failure mode for general-purpose embedders — Voyage doesn't know that *"§ 805"* and *"section 805"* are the same thing as well as a literal string match does. Concatenating `section_ref` into the BM25 document is a cheap structural fallback. `metadata.uscode_citation` is *not* in the BM25 view in v0.1 — hour 6's probe predicted the U.S.C.-notation failure mode and it didn't materialize at FDCPA's single-citation-system corpus. The fix is one line; the empirical case for it isn't there yet. v0.2 reconsiders when corpus expands to a second citation system (Reg F is CFR-numbered).

> **The principle:** Cache invalidation has clear semantics when the cache key matches what changes. Per-source caching for per-source data; per-query caching only for per-query data. And: structural fallbacks belong in the BM25 view, but only when measurement shows the dense path can't cover them.

---

← back to [`README.md`](./README.md)
