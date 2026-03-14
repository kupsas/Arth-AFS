# Arth

Personal finance transaction pipeline with a SQLite database and FastAPI backend. Reads raw Indian bank statements, classifies transactions using deterministic rules + LLM, stores results in SQLite, and exposes them via a REST API.

## Quick Start

```bash
# 1. Install dependencies
python3 -m pip install -r requirements.txt

# 2. Set up API keys
cp .env.example .env
# Edit .env with your OpenAI / Anthropic / Google API keys

# 3. Populate the database (all 4 sources)
python3 -m pipeline.run --all-sources          # full pipeline with LLM
python3 -m pipeline.run --all-sources --llm none  # rules-only, no LLM

# 4. Run the API server
uvicorn api.main:app --reload --port 8000
# Swagger UI at http://localhost:8000/docs
```

## How It Works

```
Raw Statement (.txt / .csv / .pdf)
        |
   [1] Parse          -- source-specific parser (HDFC savings, ICICI, CC)
        |
   [2] Transform      -- bank-agnostic: assign IDs, ISO dates, direction, amounts
        |
   [3] Rules Classify -- deterministic: channel, txn_type, upi_type where possible
        |
   [4] LLM Classify   -- fills counterparty, category, remaining types
        |
   [5] Write SQLite   -- dedup by content_hash; backfill NULLs on re-runs
```

Adding a new bank = write one parser file. Everything else is bank-agnostic.

## API Endpoints

**Transactions** (`/api/transactions`)
- `GET /` — List with filters: `date_from`, `date_to`, `account_id`, `direction`, `category`, `search`, `page`, `page_size`, `sort_by`
- `GET /{id}` — Single transaction
- `PATCH /{id}` — Update mutable fields (counterparty, category, txn_type, notes, is_reviewed)
- `PATCH /bulk` — Bulk update (e.g. mark multiple as reviewed)

**Pipeline** (`/api/pipeline`)
- `POST /run` — Trigger a pipeline run. Body: `{ "source_key": "hdfc_savings" | "all", "llm_model": "auto" | "none" }`
- `GET /runs` — List past pipeline runs
- `GET /runs/{id}` — Single run status (for polling)

**Health:** `GET /health`

## Environments

| Environment | DB file             | How to use                            |
| ----------- | ------------------- | ------------------------------------- |
| prod        | `data/arth.db`      | `uvicorn api.main:app --port 8000`    |
| test        | `data/arth_test.db` | `APP_ENV=test uvicorn api.main:app --port 8001` |
| pytest      | in-memory SQLite    | `pytest tests/` (no env var needed)   |

## LLM Model Strategy

The pipeline uses a **multi-model fallback chain** so rate limits or outages on any one provider don't block classification.

**Fallback order:**
1. `gemini-3.1-flash-lite` (primary — best quality-to-cost ratio)
2. `gemini-2.5-flash` (same provider, slightly costlier)
3. `claude-haiku-4-5` (Anthropic — different provider)
4. `gpt-5-mini` (OpenAI — different provider)

Full benchmark results and methodology in `docs/evaluations/llm-benchmark-2026-03/`.

## Repository Structure

```
Arth-api/
  api/                       # FastAPI backend
    __init__.py
    main.py                    App entry point, CORS, lifespan, /health
    database.py                Engine, session factory, init_db()
    models.py                  SQLModel table definitions (Transaction, PipelineRun)
    dependencies.py            FastAPI dependency injection (get_session)
    routes/
      transactions.py          Transaction CRUD, filtering, bulk update
      pipeline.py              Trigger runs, list runs, run status

  pipeline/                  # Classification pipeline
    config.py                  Configuration (models, pricing, paths, fallback chain)
    models.py                  Pydantic models & enums (ParsedTransaction, CanonicalTransaction)
    parsers/                   Source-specific parsers
      base.py                    Abstract base class
      hdfc_savings.py            HDFC savings .txt parser
      hdfc_cc.py                 HDFC credit card .csv parser
      icici_savings.py           ICICI savings .pdf parser
    transformer.py             ParsedTransaction -> CanonicalTransaction
    rules_classifier.py        Deterministic classification rules
    llm_classifier.py          LLM abstraction (multi-model fallback, caching, token tracking)
    db_writer.py               SQLite writer with content-hash dedup + backfill
    prompts.py                 Prompt loader (reads from prompts/ YAML files)
    writer.py                  Legacy CSV output (--csv flag)
    validator.py               Compare pipeline output vs GSheet ground truth
    run.py                     CLI entry point

  prompts/                   # Prompt templates (YAML, safe to commit)
    classify_single_pass.yaml
    enums.yaml
    few_shot_examples.yaml

  data/
    arth.db                  Production SQLite database (gitignored)
    arth_test.db             Test SQLite database (gitignored)
    output/                  Legacy CSV output (gitignored)
    .llm_cache/              Cached LLM responses (gitignored)

  tests/
    test_db_and_api.py         DB operations + API endpoint tests (TestClient)
    test_pipeline_e2e.py       Full pipeline accuracy regression test (slow, uses LLM)
    test_prompt_snapshots.py   Golden snapshot tests for prompt rendering
    test_prompt_yaml.py        Enum consistency checks across YAML and Python
    test_prompt_loader.py      Prompt loader unit tests
    fixtures/                  Golden prompt/response JSON fixtures

  docs/
    personal-data/           Raw bank statements + GSheet ground truth (gitignored symlink)
    evaluations/             Archived benchmark results & evaluation tools
    data-notes/              Design notes from earlier work

  .env / .env.example        API keys and config (`.env` gitignored)
  requirements.txt           Python dependencies
```

## Current Accuracy (March 2026, HDFC savings dataset)

On the full HDFC savings dataset (~647 matched rows) with the latest rules + prompt tuning:

- direction, amount, channel: **100%**
- txn_type: **98.7%**
- upi_type: **98.1%**
- counterparty: **94.9%**
- counterparty_category: **93.7%**

## Data in the Database

| Source        | Transactions | Account ID       |
| ------------- | ------------ | ---------------- |
| HDFC Savings  | 1,699        | HDFC_SAL_3703    |
| HDFC CC 1905  | 952          | HDFC_CC_1905     |
| HDFC CC 5778  | 134          | HDFC_CC_5778     |
| ICICI Savings | 451          | ICICI_SAV_6118   |
| **Total**     | **3,236**    |                  |

## Key Design Notes

- **Rules first, LLM second:** Moving classification into deterministic rules (UPI handle analysis, P2P vs P2M detection, self-transfer indicators, merchant heuristics) dramatically reduced LLM variance and cost. LLM is only called for genuinely ambiguous counterparty names.
- **Dedup by content_hash:** SHA-256 of `(txn_date, raw_description, amount, account_id)`. Re-running the pipeline on the same statement is fully idempotent. Backfill logic fills NULLs without overwriting existing values, preserving manual corrections.
- **Double-counting awareness:** `CARD_EXPENSE` (individual CC swipe) and `CARD_PAYMENT` (paying the CC bill) both exist in the DB. Naively summing all OUTFLOWs double-counts spending. Phase 3 metrics endpoints will filter correctly by `txn_type`.
- **LLM caching:** All LLM responses are cached keyed by batch content hash. Re-running the pipeline after adding new statements only calls the LLM for genuinely new transactions.
