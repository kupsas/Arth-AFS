# Product Requirements Document – **Arth v1.0**

> **Draft date:** 10 Jul 2025   |   **Target Go‑Live:** 29 Jul 2025

---

## 1 · Problem Statement & Vision

Kupz and Aditi want a personal, agentic finance system that surfaces the *right* insights at the *right* cadence and automates rote upkeep.  Today that effort is manual spreadsheets and ad‑hoc chats.  **Arth** should:

- Automate data ingestion (bank, demat) via email scrape.
- Present a weekly snapshot of key health metrics.
- Lay the foundation for future chat‑based Q&A and automations.

---

## 2 · Goals & Non‑Goals (v1)

### Goals (qualitative)

1. Run *simple automations* that load data without human copy‑paste.
2. Display *simple key metrics* answering the Day‑1 question set.
3. Be engaging and trustworthy enough that both users open it at least weekly.

### Non‑Goals for v1

- Mobile app, push alerts, Telegram/WhatsApp notifications.
- Regulatory Account‑Aggregator (AA) integrations (not possible as we are not an organisation).
- Advanced risk simulations, shock tests, or detailed DR orchestration.
- Third‑party viewer access (e.g., CA, parents).

---

## 3 · Personas & Stakeholders

| Persona   | Role                                   | Needs                                                                    |
| --------- | -------------------------------------- | ------------------------------------------------------------------------ |
| **Kupz**  | Power user – product & data tinkerer   | Fast access to numbers; ability to tweak scripts; exploratory Q&A later. |
| **Aditi** | Power user – detail‑oriented validator | Clear, accurate snapshots; trust in data pipeline; minimal manual work.  |

No external viewers in v1.

---

## 4 · Scope & Feature List

| Feature Area                   | v1 Deliverable                                                                             | Notes                                                                        |
| ------------------------------ | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| **Data Ingestion**             | Email‑scraper ETL jobs for 2 bank a/cs + 2 demat a/cs; weekly spreadsheet back‑fill pilot. | Regex/lib details will live in Cursor scripts.                               |
| **Storage**                    | Postgres schema (assets, liabilities, transactions, holdings, metrics).                    | Manual *edit scripts* (no UI) for every table.                               |
| **Calc Engine**                | Functions to answer Day‑1 questions (see §6).                                              | Unvested RSUs considered 0 value. Straight‑line depreciation for bike/house. |
| **Dashboard v0.x**             | Web page (React or HTMX) surfacing key metrics + minimal charts.                           | Dark‑mode, brand tone TBD later.                                             |
| **Security**                   | AES‑256 at rest; column‑level enc on PII; keys via free‑tier cloud KMS.                    | Cheapest viable solution.                                                    |
| **Automation Layer (Layer 0)** | Scheduled weekly ETL run + metric refresh.                                                 | No rule‑based alerts yet.                                                    |

---

## 5 · Success Metrics

1. **Monthly Active Usage (MAU):** # distinct logins over trailing 30 days (target: open >= once/week per user).
2. **Report Accuracy:** % of dashboard rows whose value matches ground‑truth spreadsheet within tolerance. Baseline target 95 %.  (Ground‑truth updated manually during pilot.)

Metric tree beyond these two is deferred.

---

## 6 · Functional Requirements & Acceptance Criteria

**Day‑1 Question Catalogue**

| ID  | Question                                              | Acceptance Test (GIVEN‑WHEN‑THEN)                                                                                                                                           |
| --- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Q1  | Total net worth *now*                                 | **GIVEN** latest asset + liability rows**WHEN** dashboard refresh runs**THEN** `net_worth = Σ assets – Σ liabilities`, displayed in ₹ lakhs, ≤ ₹1 tolerance to spreadsheet. |
| Q2  | Breakdown of assets/liabilities by category → holding | **THEN** table shows rows aggregated by `category > subcategory > symbol`; matches spreadsheet grouping.                                                                    |
| Q3  | % net worth in employer equity                        | **THEN** `(vested_value ÷ net_worth)` displayed; unvested RSU = 0.                                                                                                          |
| Q4  | Net‑worth Δ DoD, MoM, YoY                             | **THEN** three deltas compute using prior day, prev month end, prev FY same date.                                                                                           |
| Q5  | Top‑3 assets driving ≥ 80 % of Δ last quarter         | **THEN** SQL query `ORDER BY abs(delta) DESC LIMIT 3`, cumulative share ≥ 0.8.                                                                                              |
| Q6  | First low‑yield asset to reallocate                   | **THEN** asset with lowest `yield / risk‑score` flagged.                                                                                                                    |
| Q7  | Active income streams list                            | **THEN** table shows gross, net, variance vs prior period.                                                                                                                  |
| Q8  | Comp split fixed vs variable vs equity                | **THEN** pie chart + percentages.                                                                                                                                           |
| Q9  | Expense categories ranked                             | **THEN** bar chart sorted by share; includes YoY growth column.                                                                                                             |
| Q10 | 3‑, 6‑, 12‑mo savings‑rate trends                     | **THEN** line chart with confidence intervals from historical std‑dev.                                                                                                      |
| Q11 | # months with negative surplus                        | **THEN** count of months in trailing 12 where `(income – expense) < 0`.                                                                                                     |
| Q12 | Cash runway (months)                                  | **THEN** `cash ÷ avg_monthly_core_expense`, rounded 0.1.                                                                                                                    |
| Q13 | Insurance cover gap                                   | **THEN** current cover vs rule‑of‑thumb (10× expenses OR 15× income).                                                                                                       |
| Q14 | Emergency fund gap                                    | **THEN** current EF vs targets (6/9/12 mo).                                                                                                                                 |
| Q15 | Projected taxable income & rates                      | **THEN** table: taxable income, deductions, avg & marginal rates.                                                                                                           |
| Q16 | Section‑wise utilisation (80C, 80D, etc.)             | **THEN** utilisation % per section.                                                                                                                                         |
| Q17 | Unrealised gains / losses (ST, LT)                    | **THEN** two rows with totals by holding period.                                                                                                                            |

---

## 7 · Data Sources & Quality Controls

- **Sources:** Email inbox → ETL script → Postgres.
  - Bank senders: `alerts@bank1.com`, `no-reply@bank2.com` (actual list in Cursor).
  - Demat senders likewise.
- **Refresh cadence:** weekly (Friday 20:00 IST cron).
- **Audits:** Manual spreadsheet cross‑check during first 3 months.
- **Bad‑data Handling:** Discrepancies logged; fixed via edit scripts; flagged row relaunched in next refresh.

---

## 8 · User Experience (Placeholder)

- v0.x: Single‑page web dashboard.
- Components TBD (future wireframe).  Expect \~3 metric cards on top, then charts/tables per section.
- Tone: conversational, quick humor (same style as CG prompt).

---

## 9 · Security & Privacy

- **Encryption:** AES‑256 disk; column‑level on PII.  Keys in AWS KMS (free tier).
- **Auth:** Basic password for v1; consider Passkey later.
- **No DR SLA in v1** (trade‑off): snapshots manual; accept potential data loss ≤ 1 week.

---

## 10 · Tech Stack & APIs (moderate detail)

| Layer     | Choice                                                       | Rationale                                            |
| --------- | ------------------------------------------------------------ | ---------------------------------------------------- |
| ETL       | Python 3.12, Pydantic models                                 | Rich email parsing libs, Cursor co‑pilot friendly.   |
| DB & Calc | Postgres 16; SQLModel (or SQLAlchemy)                        | Familiar, strong typing, cheap hosting.              |
| API       | FastAPI REST (OpenAPI spec auto‑gen)                         | Simple, async, auto‑docs for future GraphQL gateway. |
| Dashboard | React + Vite **or** HTMX + Django templates                  | Pick during implementation.                          |
| Infra     | Fly.io free tier (Postgres + app) or Render free web service | Keeps cost ≈ \$0.                                    |
| CI/CD     | GitHub Actions; `black`, `ruff`, `pytest`                    | Enforces style & tests.                              |

---

## 11 · Risks & Mitigations

| Risk                        | Probability | Impact           | Mitigation                         |
| --------------------------- | ----------- | ---------------- | ---------------------------------- |
| Email format drift          | Med         | High (data gaps) | Unit tests on regex; manual audit. |
| Time crunch (19‑day window) | High        | Med              | Thin slice; defer nice‑to‑haves.   |
| Free‑tier infra limits      | Med         | Low              | Monitor quota; upgrade if needed.  |

---

## 12 · Timeline & Milestones

| Date       | Milestone                                                     |
| ---------- | ------------------------------------------------------------- |
| **12 Jul** | Repo scaffold + Postgres schema committed.                    |
| **15 Jul** | Email parser working on sample inbox; unit tests pass.        |
| **18 Jul** | Calc engine returns correct results for 8/17 Day‑1 questions. |
| **21 Jul** | All Day‑1 calcs green; dashboard skeleton shows JSON.         |
| **24 Jul** | Basic charts/cards live; edit scripts tested.                 |
| **27 Jul** | Security hardening; end‑to‑end test with real data.           |
| **29 Jul** | 🎉 v1 Go‑Live (Kupz’s birthday).                              |

---

## 13 · Open Questions & Future Notes

1. Wireframe specifics (layout, chart library) – TBD.
2. Rule‑based alerts & chat agent – post v1.
3. DR upgrade (RPO 24 h) – post v1 if needed.
4. Account‑Aggregator or brokerage APIs – revisit if AA becomes affordable.

---

*End of PRD v1 (ready for line‑by‑line comments in canvas).*

