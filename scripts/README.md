# Scripts

One-time setup and utility scripts. These are not part of the main pipeline or API — they're tools for first-run setup, database migration, and benchmark preparation.

---

## `discover_emails.py`

**When to use:** First-time Gmail API setup, or to explore what bank email senders and subjects exist in your inbox before writing a new email parser.

**What it does:**
1. Runs the OAuth2 browser consent flow (creates `data/gmail_token.json`)
2. Searches your Gmail inbox for known bank alert senders
3. Prints a breakdown of email subjects and counts — useful for confirming which email formats exist before committing to a parser

```bash
python3 scripts/discover_emails.py
```

> This is the "pre-server" OAuth path. If the API server is already running, you can also use `GET /api/scraper/oauth/init` to get a browser URL and complete OAuth without stopping the server.

**Output example:**
```
Sender: alerts@hdfcbank.net
  "debited via Credit Card"   →  47 emails
  "UPI txn"                   →  112 emails
  ...
```

This output is what you use to write the `can_parse(sender, subject)` method of a new email parser.

---

## `migrate_db.py`

**When to use:** If you have a database created before Phase 4 (the email scraper) and want to upgrade its schema without losing data.

**What it does:** Idempotently adds the Phase 4 columns and tables to an existing database:
- Adds `source_type` column to `transactions` (defaults to `"statement"` for all existing rows)
- Adds `gmail_message_id` column to `transactions` (defaults to `NULL`)
- Creates the `processed_emails` table if it doesn't exist

```bash
python3 scripts/migrate_db.py
```

This script is **idempotent** — safe to run multiple times on a database that has already been migrated. It checks for column/table existence before making changes.

> **Not needed for new databases.** If you're starting fresh (running `init_db()` after Phase 4 was merged), the schema is created correctly from the start.

---

## `export_benchmark.py`

**When to use:** When refreshing the LLM benchmark test fixture with new ground-truth examples.

**What it does:** Samples transactions from the GSheet ground-truth CSV and exports them in the JSON format expected by the benchmark runner (`benchmark_20.json`). The export focuses on the hard-to-classify cases — the ones that actually differentiate models.

```bash
python3 scripts/export_benchmark.py
```

Output goes to `docs/evaluations/llm-benchmark-2026-03/benchmark_20.json`.

After exporting, run the benchmark to see how the current prompt and model stack performs:
```bash
python3 docs/evaluations/llm-benchmark-2026-03/benchmark.py
```
