# regulated-rag

**Citation-grounded, refusal-bounded retrieval for regulated-domain corpora.**

The single sentence this repo exists to prove: *citation grounding and refusal-on-low-confidence belong in code, not in prompts; treating them as architectural enforcement boundaries makes RAG defensibly auditable in regulated domains.*

The third pillar of a portfolio thesis on defensible AI in regulated finance:

- **[FinAgent OS](https://github.com/RZ-Logic/finagent-os)** — governance: SOX-defensible properties enforced as architecture, not promised as documentation
- **finance-agent-evals** *(v0.1.0 ships May 31, 2026)* — evaluation: AI-as-actor under SOX with PCAOB AS 2201 severity tiers structurally embedded in the eval scoring scheme
- **regulated-rag** *(this repo, v0.1 in active development)* — retrieval: the layer that decides what evidence the model sees, with the stochastic generation stage bounded by deterministic checks on both sides

## Status

**v0.1.0 in active development. Expected ship date: May 4, 2026.**

The full README — including the *"Where is the LLM?"* architectural enumeration, build decisions narrative, honest limitations, and prior art positioning — lands when v0.1 ships.

## License

MIT

---

*Built by [Rizwan Ahmed](https://github.com/RZ-Logic) — ACCA-qualified, AI architecture for regulated finance.*