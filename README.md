# Arth

Personal finance transaction pipeline. Reads raw Indian bank statements, classifies transactions using deterministic rules + LLM, and outputs enriched canonical data.

## Quick Start

```bash
# 1. Install dependencies
python3 -m pip install -r requirements.txt

# 2. Set up API keys (need at least one provider for LLM classification)
cp .env.example .env
# Edit .env with your OpenAI / Anthropic / Google API keys

# 3. Run the pipeline
python3 -m pipeline.run                    # full pipeline with LLM (auto fallback)
python3 -m pipeline.run --llm none         # rules-only, no LLM
python3 -m pipeline.run --validate         # also compare against GSheet ground truth
```

## How It Works

```
Raw Statement (.txt/.csv/.pdf)
        |
   [1] Parse          -- source-specific parser (HDFC savings, ICICI, CC)
        |
   [2] Transform      -- bank-agnostic: assign IDs, ISO dates, direction, amounts
        |
   [3] Rules Classify -- deterministic: channel, txn_type, upi_type where possible
        |
   [4] LLM Classify   -- fills counterparty, category, remaining types
        |
   [5] Write CSV       -- canonical output to data/output/
```

Adding a new bank = write one parser file. Everything else is bank-agnostic.

## LLM Model Strategy

The pipeline uses a **multi-model fallback chain** so rate limits or outages on any one provider don't block classification. Set `LLM_MODEL=auto` in `.env` (the default).

**Fallback order:**
1. `gemini-3.1-flash-lite` (primary -- best quality-to-cost ratio)
2. `gemini-2.5-flash` (same provider, slightly costlier)
3. `claude-haiku-4-5` (Anthropic -- different provider)
4. `gpt-5-mini` (OpenAI -- different provider)

This was decided via a comprehensive benchmark in March 2026. Full results and methodology in `docs/evaluations/llm-benchmark-2026-03/`.

## Repository Structure

```
Arth/
  pipeline/                  # Production pipeline code
    config.py                  Configuration (models, pricing, paths, fallback chain)
    models.py                  Pydantic models & enums (ParsedTransaction, CanonicalTransaction)
    parsers/                   Source-specific parsers
      base.py                    Abstract base class
      hdfc_savings.py            HDFC savings .txt parser
    transformer.py             ParsedTransaction -> CanonicalTransaction
    rules_classifier.py        Deterministic classification rules
    llm_classifier.py          LLM abstraction (multi-model fallback, caching, token tracking)
    prompts.py                 Prompt templates for LLM classification
    writer.py                  CSV output
    validator.py               Compare pipeline output vs GSheet ground truth
    run.py                     CLI entry point

  data/
    output/                  Pipeline output CSVs
    test/                    Benchmark fixtures
    .llm_cache/              Cached LLM responses (content-keyed, model-independent)

  docs/
    personal-data/           Raw bank statements + GSheet ground truth
    evaluations/             Archived benchmark results & evaluation tools
    data-notes/              Design notes from earlier work

  .cursor/rules/             Project context rules for Cursor AI agents
  .env / .env.example        API keys and config
  requirements.txt           Python dependencies
```

## Ground Truth

`docs/personal-data/GSheet_Transactions.csv` contains ~648 manually-classified transactions. This is the benchmark for measuring pipeline accuracy. The validator matches by `raw_description` and compares: direction, amount, txn_type, channel, upi_type, counterparty, counterparty_category.

## Current Accuracy (March 2026)

On the full 648-row HDFC savings dataset:
- direction, amount, channel: **100%**
- txn_type: **91%**
- upi_type: **93.5%**
- counterparty: **47%** (naming mismatches -- needs prompt improvement)
- counterparty_category: **60%** (primarily Uber/cab driver misclassification)

Next step: prompt engineering to push counterparty + category accuracy higher.
