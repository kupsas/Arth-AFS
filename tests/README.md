# Tests

pytest test suite for the Arth pipeline, API, and email scraper. 86+ tests across unit, integration, and end-to-end coverage.

---

## Running Tests

```bash
# Run all tests
pytest tests/

# Run a specific file
pytest tests/test_email_parsers.py

# Run with verbose output (see individual test names)
pytest tests/ -v

# Skip slow/expensive tests (LLM calls, etc.)
pytest tests/ -m "not slow"

# Run with coverage report
pytest tests/ --cov=. --cov-report=term-missing
```

Tests use an **in-memory SQLite database** via `conftest.py`. No `.env` required, no external services needed.

---

## Test Files

| File | What it tests | Count |
|---|---|---|
| `test_email_parsers.py` | `can_parse()` routing + full field assertions against real HTML email fixtures | ~50 |
| `test_reconciliation.py` | 5 core reconciliation scenarios: email→reconciled upgrade, statement-only insert, cross-account false positive guard, manual edit survival, content-hash dedup | 16 |
| `test_orchestrator.py` | Full scrape cycle paths: processed/skipped/failed + already-processed dedup, using mock `GmailClient` and real fixture HTML | 20 |
| `test_db_and_api.py` | DB operations + API endpoint tests via FastAPI `TestClient` | — |
| `test_pipeline_e2e.py` | End-to-end pipeline (parse → transform → classify → write) | — |
| `test_prompt_yaml.py` | YAML prompt files load correctly and contain all required keys | — |
| `test_prompt_loader.py` | Prompt loader correctly interpolates `{variable}` placeholders | — |
| `test_prompt_snapshots.py` | Rendered prompts match golden snapshots — catches accidental prompt changes | — |

---

## Fixtures

| Path | What it is |
|---|---|
| `tests/fixtures/email_samples/` | Real HTML email bodies captured from bank alert emails. Gitignored (contains account-number hints). |
| `tests/fixtures/golden_single_pass.json` | Golden snapshot of the rendered single-pass prompt |
| `tests/fixtures/golden_two_pass_fields.json` | Golden snapshot of the two-pass fields prompt |
| `tests/fixtures/golden_two_pass_category.json` | Golden snapshot of the two-pass category prompt |

**Regenerate golden snapshots** (needed after intentional prompt changes):
```bash
python3 tests/capture_golden_snapshots.py
```

---

## Key Patterns

### In-memory SQLite with StaticPool

All tests that touch the database use an in-memory SQLite with `StaticPool`. This is non-negotiable: without `StaticPool`, every `Session()` gets its own independent in-memory database — tables created in fixture setup don't exist when the test runs.

`conftest.py` sets this up automatically. Use the `session` fixture from there; don't create sessions manually in tests.

### Patch at the usage site

When mocking imports, patch at the site where the name is **used**, not where it's **defined**:

```python
# Correct — the route module imported the name at load time; patch its reference
patch("api.routes.scraper.trigger_now")

# Wrong — the route already holds a reference to the original; this patch is invisible
patch("scraper.scheduler.trigger_now")
```

### Disable LLM calls in tests

Tests set `LLM_MODEL = "none"` to skip real LLM API calls and run rules-only:

```python
import pipeline.config as cfg
cfg.LLM_MODEL = "none"
```

Patch the attribute on the imported module object. Don't re-import the string — you'll get a copy that doesn't affect the running code.

### Mock GmailClient

`test_orchestrator.py` uses a mock `GmailClient` that returns pre-loaded HTML fixtures from `tests/fixtures/email_samples/`. This lets the orchestrator tests run the full parse → classify → write path without real Gmail credentials or network calls.

---

## `conftest.py`

Shared fixtures available to all test files:

- `session` — in-memory SQLite session (StaticPool), auto-rollback between tests
- `client` — FastAPI `TestClient` wired to the test session (dependency override)
- Any shared transaction or pipeline run setup used across multiple test files
