# WhyLine — The Agent That Can Explain Why

**Open Agent Hackathon 2026 · Track 02: The Agent That Can Explain Why**
Team: **Shimi Studio Agents** (Sun Raz)

## The problem

Most AI answers collapse a chain of reasoning into a single confident paragraph.
You get the *what*, never the *why* — no sources, no cross-checks, no way to tell
whether one website said something once or whether five independent kinds of
evidence actually agree. For decisions that matter (investments, policy, health,
research), an answer without a visible evidence chain is a guess wearing a suit.

## What WhyLine does

Given a complex question, WhyLine runs a four-stage evidence pipeline:

```
QUESTION ─► [1] DECOMPOSE ─► [2] HARVEST ─► [3] CROSS-VALIDATE ─► [4] SYNTHESIZE ─► ANSWER
            sub-questions     5 source      claim clustering      why-chain +
            (facts needed)    classes       across sources        confidence
```

1. **Decompose** — the question is broken into 3–5 concrete, checkable sub-questions
   (the facts you would need to verify in order to answer it).
2. **Harvest** — every sub-question fans out to **five independent source classes**,
   each with a tailored query, in parallel:

   | Source class | What it contributes |
   |---|---|
   | Wikipedia | encyclopedic baseline facts |
   | News (Google News RSS) | recent developments, reporting |
   | Crossref | peer-reviewed academic evidence |
   | Bing | open web breadth |
   | Marginalia | independent, non-commercial long tail |

3. **Cross-validate** — findings are clustered into claims by word-overlap, and each
   claim is marked `corroborated` (2+ independent sources) or `single-source`.
   Junk results that share no keywords with the question are dropped — the agent
   prefers *no* evidence to garbage evidence.
4. **Synthesize** — an evidence-backed answer with a **visible WHY-chain**
   (sub-finding → conclusion), the corroboration matrix, contradictions that remain,
   and a **confidence score derived from cross-source agreement counts** — not from
   the model's self-report.

## Quick start

```bash
python3 ask.py "Why did FTX collapse and what happened to customer funds?"
```

Optional: full run saved as JSON for downstream tools:

```bash
python3 ask.py "Why is SQLite the most deployed database?" --json-out report.json
```

No keys, no installs, no dependencies — pure Python 3 standard library.

## Reasoning layer: NVIDIA Nemotron

WhyLine's reasoning (decomposition and synthesis) is powered by
**NVIDIA Nemotron** through the NVIDIA API (`integrate.api.nvidia.com`,
OpenAI-compatible) when a key is present:

```bash
export NVIDIA_API_KEY=nvapi-...
export NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b   # default
python3 ask.py "your question"
```

Without a key the agent runs in **Deterministic Mode** — the full pipeline still
executes (entity extraction, fan-out harvest, cross-validation, extractive
synthesis), so WhyLine is fully functional with zero paid services and degrades
gracefully instead of failing. Every run reports which engine produced the answer.

## Example run (Deterministic Mode, no keys)

```
WHY-LINE AGENT
========================================================================
QUESTION: Why did FTX collapse and what happened to customer funds?
[1/4] decomposed into 3 sub-questions:
      - FTX overview
      - FTX collapse happened explained
      - FTX criticism and risks
[2/4] 38 unique evidence items from 3 sources: Crossref, News, Wikipedia
[3/4] 2/15 claims corroborated by 2+ independent sources
[4/4] done in 4.6s — synthesis mode: deterministic-extractive
========================================================================
WHY-CHAIN:
CORROBORATED: Senators slam FTX, Sam Bankman-Fried and back crypto regulation
              (sources: Crossref, News, Wikipedia)
CORROBORATED: FTX Collapse and systemic risk spillovers from FTX Token to
              major cryptocurrencies (sources: Crossref, Wikipedia)
CONFIDENCE: 92/100 — derived from cross-source corroboration, not self-report.
```

## Design decisions worth noticing

- **Evidence or nothing.** Any finding that shares zero keywords with the question
  is discarded. Sources that serve junk (bot-blocked pages) are skipped rather than
  polluting the matrix.
- **Independence is enforced.** Corroboration counts *source classes*, not result
  count — ten links from one search engine never inflate confidence.
- **The WHY-chain is inspectable.** Every claim in the final answer links back to
  which sources support it; single-source claims are shown as open contradictions
  instead of being laundered into confident prose.
- **Confidence is computed, not felt.** The score is an arithmetic function of
  corroboration counts — auditable in the JSON output.

## Team & development

- **Team:** Shimi Studio Agents — solo builder, built end-to-end during the hackathon window.
- **Pre-existing components declared:** none — the agent code, pipeline design, and
  documentation were written during the hackathon (Oct 22–27, 2026). It uses only
  the Python 3 standard library and public APIs (Wikipedia, Crossref, Google News RSS,
  Bing, Marginalia).
- No API keys, passwords, or secrets are stored in this repository.

## Repository layout

```
ask.py          the whole agent (stdlib-only, single file)
README.md       this file
report.pdf      generated example run report
demo/           demo artifacts
```
