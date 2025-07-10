# Arth – Technical Requirements Document (TRD) v1.0

> **Status:** Draft – July 10 2025\
> **Owners:** Kupz (Product), CG (Engineering Partner)

---

## 0 · Context & Scope

| Item                  | Detail                                                                                                                                                          |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Objective**         | Build an internal, agentic personal‑finance system that automatically ingests data, answers the Day‑1 question‑set in the PRD, and surfaces a weekly dashboard. |
| **In‑scope**          | Email scraping via Gmail API, nightly ETL, calculation engine, HTMX dashboard, CLI overrides, managed Postgres, two power‑users only.                           |
| **Out‑of‑scope (v1)** | Mobile app, Account‑Aggregator APIs (AA), complex risk simulations, enterprise‑grade fail‑over.                                                                 |
| **Go‑live target**    | **29 Jul 2025** (Kupz’s birthday).                                                                                                                              |

---

## 1 · Technology Stack

| Layer              | Choice                                                         | Key Libraries / Tools                                               | Rationale                                                       |
| ------------------ | -------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Language**       | **Python 3.12**                                                | SQLModel, Pydantic v2, FastAPI, Alembic, HTMX templates with Jinja2 | Modern typing + async support; rich ecosystem.                  |
| **Web / UI**       | **HTMX + Tailwind CSS**                                        | shadcn/ui (utility classes), Alpine JS (sprinkles)                  | Server‑render simplicity, tiny JS footprint, rapid prototyping. |
| **Data**           | **Postgres 16 (managed)**                                      | pgvector (future), pg\_cron (optional)                              | Mature RDBMS, cheap managed offerings, strong SQL analytics.    |
| **Infrastructure** | **Docker → Fly.io / Render** (TBD at deploy)                   | Dockerfiles, GitHub Actions                                         | Push‑to‑deploy, free tier, global POPs (Fly).                   |
| **Auth**           | Google OAuth 2 (flow w/ `access_type=offline`)                 | google‑api‑python‑client                                            | Long‑lived refresh tokens for unattended sync jobs.             |
| **Testing**        | pytest, pytest‑cov, tox, Ruff, Black, mypy (`--strict` scoped) | 80 %+ coverage, style & static‑type gates.                          |                                                                 |
| **Observability**  | JSON structured logs → host log‑drain, Grafana Loki (optional) | E‑mail alerts on `ERROR`/`CRITICAL`.                                |                                                                 |
| **CI/CD**          | GitHub Actions                                                 | Build, lint, test, push image, deploy.                              |                                                                 |

---

## 2 · High‑Level Architecture

```mermaid
flowchart TD
    Gmail[Gmail API]
    ETL[ETL Worker(s)]
    DB[(Postgres DB)]
    Calc[Calc Engine]
    API[FastAPI + HTMX UI]
    Alert[Email Alert (critical)]
    CLI[CLI Edit Scripts]

    Gmail -->|"OAuth2 / JSON"| ETL
    ETL -->|"parse & load"| DB
    Calc <--|"SQL views"| DB
    API -->|"REST/HTMX"| Calc
    CLI -->|"manual overrides"| DB
    Calc --> API
    API --> Alert
```

*Single Docker image* houses ETL, API, UI to keep ops simple.

---

## 3 · Directory Structure

```text
arth/
 ├─ src/
 │   ├─ models/        # SQLModel ORM classes, enums
 │   ├─ etl/           # Gmail client, parsers, loaders
 │   ├─ calc/          # KPI functions + SQL helpers
 │   ├─ api/           # FastAPI routers & HTMX endpoints
 │   ├─ cli/           # `arth edit ...` entry‑points
 │   └─ util/          # logging, settings, email helpers
 ├─ scripts/           # one‑off backfill, data dumps
 ├─ tests/             # unit + integration + fixtures
 ├─ Dockerfile
 ├─ alembic/
 ├─ pyproject.toml
 └─ docs/              # PRD, TRD, calc‑dictionary, etc.
```

---

## 4 · Database Specification

### 4.1 Core Schema

| Table            | Columns (PK ★, FK →)                                                                                                                                                                                         | Notes / Indexes                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------- |
| `accounts` ★     | `id`, `type` ENUM(bank, broker, card, wallet), `name`, `identifier`, `currency`, `opened_on`                                                                                                                 | `UNIQUE(identifier)`            |
| `assets` ★       | `id`, `symbol`, `isin`, `category` ENUM(equity, mf, bond, cash, property), `sub_category`, `currency`                                                                                                        | `(category, symbol)` index      |
| `transactions` ★ | `id`, `account_id` → `accounts`, `asset_id` → `assets` NULL, `posted_at` TIMESTAMPTZ, `amount` NUMERIC(18,2), `currency`, `txn_type` ENUM(debit, credit, dividend, fee, emi, interest), `raw_source_id` TEXT | `(account_id, posted_at)` BTREE |
| `holdings` ★     | `asset_id` → `assets`, `qty` NUMERIC, `cost_basis`, `mkt_value`, `as_of` DATE                                                                                                                                | nightly snapshot                |
| `metrics` ★      | `id`, `calc_id`, `period` ENUM(day, week, month), `value` NUMERIC, `as_of` DATE                                                                                                                              | precalculated responses         |

### 4.2 Enumerations

- `account.type`, `asset.category`, `txn.txn_type` **🔲 TBD** – to be finalised once first‑wave sources sampled.

### 4.3 Indexes & Constraints

- Primary keys = surrogate `BIGINT` (Snowflake IDs optional).
- Foreign keys ON DELETE CASCADE where safe.
- All monetary columns store *base currency* per row, future FX handled by view.

---

## 5 · Data Ingestion & ETL

| Phase          | Implementation                                            | Detail                                                       |
| -------------- | --------------------------------------------------------- | ------------------------------------------------------------ |
| **Auth**       | `google-auth` + refresh‑token cache                       | Offline access; token encrypted (Fernet) in DB.              |
| **Back‑fill**  | `scripts/backfill.py` one‑shot                            | `users.messages.list` iterate history → enqueue IDs → parse. |
| **Daily sync** | `cron 02:00 IST` inside container                         | Use `historyId` delta; throttle 10 req/s.                    |
| **Parse**      | Regex / BeautifulSoup per mapping sheet **🔲 Appendix B** | Subject & sender heuristics → structured dict.               |
| **Load**       | SQLModel session batch                                    | Upsert account, insert txn; commit every 250 rows.           |
| **Cleanup**    | Temp dir auto‑purge                                       | Raw bodies removed post‑parse, no blob storage.              |

---

## 6 · Calculation Engine

- **Materialised views** for expensive KPIs (`net_worth`, `cash_runway`) refreshed nightly.
- **Pure SQL** where possible; Python fallback (e.g., XIRR).
- Dictionary lives in `docs/calcs.md` (KPI ID, formula, units, edge‑case notes).
- Unvested RSUs contribute **0** until vest date.

---

## 7 · API & UI Contract

### 7.1 HTMX Routes (draft - subject to change as UX flows are finalised)

| Route            | Verb | Purpose                                   | Response              |
| ---------------- | ---- | ----------------------------------------- | --------------------- |
| `/`              | GET  | Dashboard cards & graphs                  | HTML fragment         |
| `/tx/list`       | GET  | Table with filters `account`, `date_from` | JSON (HTMX swap)      |
| `/holding/{id}`  | GET  | Fly‑out with position detail              | HTML                  |
| `/metrics/{kpi}` | GET  | JSON `{dates[], values[]}` for chart      | JSON                  |
| `/edit/txn`      | POST | Inline quick‑fix                          | 204 or form w/ errors |

### 7.2 REST (Internal)

- `/v1/healthz` → 200 OK.
- `/v1/trigger/sync` (POST, admin only) – fires ETL immediately.

CSRF: double‑submit cookie; Session: signed JWT, 12 h expiry.

---

## 8 · CLI Tools

```
$ arth edit add‑txn --account 1 --date 2025‑07‑01 --amount 2500 --type fee [--dry‑run]
$ arth edit update‑holding --id 12 --qty 150
$ arth edit reprice‑asset --symbol INFY --price 1785.50 --date 2025‑07‑09
```

- Entry point: `python -m arth.cli`.
- POSIX flags; returns 0 on success, >0 on error.

---

## 9 · Orchestration & Jobs

| Job                   | Schedule (IST)       | Runner                                   | Notes                            |
| --------------------- | -------------------- | ---------------------------------------- | -------------------------------- |
| **Back‑fill**         | once at first deploy | Detached `scripts/backfill.py`           | Idempotent retry safe.           |
| **Daily sync**        | 02:00                | Cron (`bash -c python -m arth.etl.sync`) | Delta‑based.                     |
| **Nightly metrics**   | 02:30                | Cron                                     | `REFRESH MATERIALIZED VIEW ...`. |
| **Weekly audit dump** | Fri 20:00            | Cron                                     | CSV to `/tmp`, emailed to users. |

---

## 10 · Deployment Strategy

1. **Build:** `docker build -t arth:${GIT_SHA} .`
2. **Push:** `docker push registry/${GIT_SHA}`.
3. **Fly.io:** `fly deploy --image registry/${GIT_SHA}` (volumes for Postgres proxy).\
   **Render:** auto deploy from `main` on push.
4. Post‑deploy hook runs `alembic upgrade head`.
5. Zero‑downtime **optional**; v1 accepts ≤ 30 s restart.

---

## 11 · Testing & Quality Gates

| Stage           | Tool                                       | Gate           |
| --------------- | ------------------------------------------ | -------------- |
| **Lint**        | Ruff (`ruff check .`)                      | no warnings    |
| **Format**      | Black (`--check`)                          | idempotent     |
| **Static‑type** | mypy `--strict` on `src/{models,calc,etl}` | 0 errors       |
| **Unit tests**  | pytest‑cov                                 | ≥ 80 % overall |
| **Integration** | golden email fixtures, DB round‑trip       | all green      |
| **E2E smoke**   | docker‑compose up → GET `/` 200            | pass           |

CI pipeline defined in `.github/workflows/ci.yml`.

---

## 12 · Security & Data Protection

- **Secrets store:** platform env‑vars (AES‑encrypted at rest).
- **Disk enc:** managed Postgres encryption; no raw blobs stored.
- **Data retention:** DB snapshots (daily) kept 30 days → auto‑expire.
- **Access control:** Only Kupz & Aditi OAuth; CLI inside container.
- **Transport:** HTTPS enforced; HSTS 1 year.
- **Static analysis:** Ruff/mypy block undefined vars, avoiding injection bugs.

---

## 13 · Logging & Observability

| Aspect         | Setting                                                     |
| -------------- | ----------------------------------------------------------- |
| **Format**     | JSON lines: `ts`, `level`, `module`, `msg`, `extra`.        |
| **Levels**     | DEBUG (dev), INFO (prod), ERROR, CRITICAL.                  |
| **Retention**  | 7 days hot; host drains to S3‑like storage.                 |
| **Alerting**   | `level >= ERROR` triggers `sendgrid_email()` to both users. |
| **Dashboards** | Optional Grafana Loki datasource.                           |

---

## 14 · Non‑Functional Requirements

| Metric                | Target                              |
| --------------------- | ----------------------------------- |
| P95 dashboard latency | < 300 ms                            |
| Uptime (soft)         | 95 % (free‑tier reality)            |
| Data‑loss window      | ≤ 24 h (daily snapshot)             |
| Deploy downtime       | ≤ 30 s                              |
| Browser support       | Latest Chrome & Firefox (dark‑mode) |

---

## 15 · Glossary & Appendices

- **Appendix A – Enumerations & Validation Rules** 🔲 TBD
- **Appendix B – Source‑Mapping Sheet (bank/demat regex)** 🔲 TBD
- **Appendix C – KPI Dictionary (formula, units, edge‑cases)** 🔲 TBD

---

### Next Steps

1. Collect real e‑mail samples → finish **Appendix B**.
2. Lock enum lists → **Appendix A**.
3. Flesh out KPI formulas → **Appendix C**.
4. Review & sign‑off → freeze TRD v1.0 → start implementation.

---

## 16 · Implementation Plan (aligned with PRD milestones)

| Milestone                      | Target Date (2025) | Success Criteria                                                                             | 2‑3 Key Tasks                                                                                                                                                        |
| ------------------------------ | ------------------ | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **M‑0 Repo Bootstrap**         | **14 Jul**         | Repo initialised, Docker image builds locally, CI pipeline (lint + tests) green              | • Create GitHub repo and branch protections  • Add `Dockerfile`, `docker-compose.yml`, Alembic baseline  • Configure GitHub Actions with Ruff/Black/mypy/pytest jobs |
| **M‑1 Ingestion MVP**          | **18 Jul**         | ETL pulls one day of Gmail data, writes to `transactions` table                              | • Implement Gmail OAuth w/ offline token  • Build first parser (bank statement) & mapping sheet stub  • Add `arth.etl.sync` cron + backfill script                   |
| **M‑2 Calc & Dashboard Alpha** | **22 Jul**         | `net_worth`, `cash_runway` views materialised; dashboard home page renders values            | • Create SQL views & nightly refresh job  • Scaffold FastAPI + HTMX route `/`  • Simple Tailwind card components                                                     |
| **M‑3 Parser Coverage & CLI**  | **25 Jul**         | ≥ 80 % of historical emails parsed; CLI edit commands functional                             | • Add parsers for broker & credit‑card mails  • Write `arth edit add‑txn/update‑holding` commands  • Unit + integration tests hit 80 % coverage                      |
| **M‑4 Hardening & UAT**        | **28 Jul**         | Full nightly run succeeds; error alerts verified; Kupz & Aditi run UAT checklist             | • Enable email alerts on `ERROR`  • Security review (secrets, TLS)  • Manual data‑quality spot‑check CSV                                                             |
| **M‑5 Go‑Live**                | **29 Jul** 🎂      | App deployed to Fly/Render, one‑time backfill completed, daily snapshot on, dashboard shared | • Deploy image with `fly deploy` / Render  • Run backfill & verify metrics  • Create README & hand‑over docs                                                         |

*These dates assume 3–4 h/day of maker time; adjust if bandwidth shifts.*

---

*End of TRD v1.0 draft.*

