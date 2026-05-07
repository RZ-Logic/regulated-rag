# Prior Art & Acknowledgements

regulated-rag does not exist in a vacuum. The architectural decisions draw deliberately on existing work. Naming the influences is part of the rigor — the core claim asserts a gap, and naming what was sampled is what makes the gap defensible.

← back to [`README.md`](./README.md)

---

## The closest direct analog

- **[Radio-RAG (`Zakaria010/Radio-RAG`)](https://github.com/Zakaria010/Radio-RAG)** — El Kassimi, Fourati, Alouini (KAUST, Sept 2025, [arXiv 2509.09651](https://arxiv.org/abs/2509.09651)). Same shape (domain-specific RAG for legally-sensitive regulations), different stack (FAISS vs. pgvector), MCQ eval (vs. open-ended Q&A with citation), 97% retrieval accuracy on a domain-specific metric, ~12% relative improvement over naive RAG on GPT-4o. Does not address refusal as an architectural property. The differentiation here is on (a) refusal-on-low-confidence as first-class output, (b) citation grounding as post-generation deterministic check, (c) reproducibility commitments held to v0.1 rather than v1.0.

## Hybrid retrieval + reranking — established pattern

- **Cormack, Clarke, Buettcher, *"Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods"* (SIGIR 2009)** — the RRF score-combination method.
- **TraceRetriever — *"Segment First, Retrieve Better: Realistic Legal Search via Rhetorical Role-Based Queries"* (Aug 2025, [arXiv 2508.00679](https://arxiv.org/abs/2508.00679))** — legal-case retrieval via BM25 + bi-encoder vector + cross-encoder reranking. The exact retrieval triple this repo uses, in the legal-domain neighbor.
- **[`chatterjeesaurabh/Contextual-RAG-System-with-Hybrid-Search-and-Reranking`](https://github.com/chatterjeesaurabh/Contextual-RAG-System-with-Hybrid-Search-and-Reranking)** — same hybrid+rerank pattern, LangChain-orchestrated, BAAI/bge-reranker-v2-m3 reranker. Demonstrates the pattern as commodity. Differentiation here is the raw-SDK choice (no LangChain), consistent with the rest of the portfolio.
- **Cohere `rerank-v3.5` model card** — the hosted cross-encoder choice, with awareness of open-source alternatives (`bge-reranker-v2-m3`) for v0.2 cost/self-hosting flexibility.

## The approach not taken

- **RAGulating Compliance — Agarwal et al., MasterControl AI Research, *"RAGulating Compliance: A Multi-Agent Knowledge Graph for Regulatory QA"* (Aug 2025, [arXiv 2508.09893](https://arxiv.org/abs/2508.09893))** — KG/SPO multi-agent approach to regulatory QA. Different architecture with different failure modes (entity extraction quality, KG completeness, multi-agent coordination overhead). Cited explicitly to define the contrast: v0.1 is the simpler citation-grounded retrieval pattern, deliberately. KG approaches are a v2+ direction if the eval surfaces a need.
- **Multi-step retrieval and reasoning frameworks (RaR for radiology, agentic RAG patterns)** — chained retrievals decomposing complex queries. Useful for multi-hop reasoning; out of scope for citation-grounded regulatory QA in v0.1.

## Citation-grounding patterns

- **Tensorlake, *"Citation-Aware RAG: How to add Fine Grained Citations"* (Sept 2025)** — the most published-thinking-aligned reference for fine-grained citations via metadata anchors (page numbers, paragraph IDs, bounding boxes). Validates the metadata-rich chunking approach. Frames citation as a *retrieval/synthesis* property; this repo extends the pattern to citation as a *post-generation deterministic check* — the validation step that fails closed when the model cites a chunk it did not see in the retrieved set.

## Eval methodology

- **[`cheddarhub/rageval-oran`](https://github.com/cheddarhub/rageval-oran) — *"Benchmarking Vector, Graph and Hybrid RAG Pipelines for Open Radio Access Networks"* ([arXiv 2507.03608](https://arxiv.org/abs/2507.03608))** — the four eval metrics adopted here (faithfulness, answer relevance, context relevance, factual correctness) and the methodology of independent metric reporting rather than a single accuracy number.
- **Jason Liu, *"Systematically Improving RAG"*** — the eval-and-improve framing; retrieval quality is the largest lever before generation tuning.

## Retrieval methodology references

- **Anthropic, *"Introducing Contextual Retrieval"* (Sept 2024)** — the chunk-context-prepending technique. v0.1 baseline does not implement this; v0.2 adopts it after measuring the structural-chunking baseline against it. The *measurement* is what justifies adopting the technique.
- **`anthropic-cookbook/skills/contextual-embeddings`** — reference implementation for contextual retrieval, methodology only (not adopted in v0.1).
- **pgvector documentation (Supabase guide and upstream `pgvector/pgvector`)** — the Postgres-native vector indexing approach; HNSW vs. IVFFlat trade-offs.

## Architectural posture

- **FinAgent OS (this author)** — the *"Where is the AI?"* enumeration pattern, adapted as *"Where is the LLM?"* for the retrieval pipeline. The architectural principle that the stochastic component is bounded by deterministic checks transfers directly.
- **NIST AI Risk Management Framework, Generative AI Profile (NIST AI 600-1)** — the framing that AI system risk requires structural identification of where stochastic decisions occur. Read for orientation; not a binding standard for this repo.
- (LangChain and LlamaIndex were evaluated and explicitly rejected for v0.1. The framework abstractions are studied, not unknown — raw SDK is the seniority signal and the portfolio-continuity choice. See [`BUILD-DECISIONS.md`](./BUILD-DECISIONS.md) for the trade-off narrative.)

## Regulatory anchors

- **Fair Debt Collection Practices Act, 15 U.S.C. §§ 1692–1692p** — the federal statute serving as v0.1's primary corpus.
- **CFPB Regulation F (12 CFR Part 1006)** — implementing regulations for FDCPA. v0.2 corpus expansion.
- **California Department of Financial Protection and Innovation — EWA registration framework** — the state-regulatory corpus serving as v0.1's planned heterogeneous source (deferred to v0.2 per [`CORPUS-NOTES.md`](./CORPUS-NOTES.md)).

---

## Differentiation against prior art

The prior-art density above is intentional. Regulated-domain RAG, hybrid retrieval, cross-encoder reranking, and citation-via-metadata are established patterns; claiming novelty on any of them in isolation would be defensible only by ignoring the literature. **The differentiation is at the intersection.**

- **Refusal-on-low-confidence as a measured architectural property.** Sampled regulated-domain RAG implementations optimize for accuracy on questions the corpus covers. Refusal at most appears as prompt-side instruction. This repo treats refusal as a deterministic check below a tuned confidence threshold, *and* reports refusal correctness on out-of-corpus queries as a primary eval metric — making the architectural commitment empirically falsifiable rather than rhetorical.
- **Citation grounding as a post-generation deterministic check.** Tensorlake's citation-aware RAG positions citations as a retrieval-and-synthesis property: give the model metadata-rich chunks and prompt it to surface citations inline. This repo extends the pattern with a validation step that fails closed: every cited chunk ID must appear in the retrieved-top-5 set; uncited claims trigger refusal. The check is in code, not in the prompt.
- **Reproducibility held to v0.1, not v1.0.** Version-pinning every stochastic component, eval results checked into the repo, eval methodology pre-registered, transcripts hand-read for any flagged metric — these are standard practice in evaluation frameworks like UK AISI's Inspect, but not in regulated-domain RAG repos sampled. This repo treats those commitments as v0.1 deliverables, not v1.0 polish.
- **Applied to a corpus with no public RAG implementation we could find.** As of v0.1's research date, GitHub repository search returned zero results for `"FDCPA RAG"` and zero for `"earned wage access" RAG`; the closest semantically-adjacent hit (`nihanth123/agentic-rag-knowledge-assistant`) is an AWS Bedrock multi-agent demo, not regulatory retrieval; the closest CFPB-anchored repo (`cfpb/debt-collection-files`) holds design files for the model validation notice, not a RAG. GitHub's native search is the artifact searched. The corpus choice also isn't arbitrary: consumer-debt regulation is the regulatory surface area of a real fintech vertical (consumer cash advance / debt relief) where the gap between *"the model answered confidently"* and *"the model answered correctly"* carries operational and legal consequence.

The novel contribution is the intersection: enforcement-boundary architecture (citation-as-architecture, refusal-as-first-class-output, version-pinning) applied to standard hybrid retrieval, demonstrated on a regulated-domain corpus that didn't have a public RAG yet. None of the four pieces alone is novel; the intersection is the contribution.

---

← back to [`README.md`](./README.md)
