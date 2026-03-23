# Arth Phase 5 — Guideline Document (v3 — Final)

> **Created:** 22 Mar 2026 | **Last updated:** 23 Mar 2026
> **Purpose:** Strategic guideline for Cursor/Opus to build an implementation plan from. Covers the what and why; Cursor owns the how.
> **Sprint start:** 22 Mar 2026

---

## 1 · Where Arth Is Today

### What exists and works
- **Transaction pipeline:** 4 bank sources (HDFC savings, HDFC CC ×2, ICICI savings), 3,236+ transactions classified at 94–97% accuracy. Rules-first classification, LLM fallback (Gemini Flash Lite).
- **Email scraper:** Gmail API polls every 15 min, covers ~70–80% of day-to-day spending in real time. Statement reconciliation eliminates duplicates.
- **FastAPI backend:** REST API with auth, transaction CRUD, metrics (summary, categories, trends, accounts, counterparties, investment flows, expense stacking), pipeline controls, scraper management, goals CRUD, recurring patterns, reminders.
- **Next.js dashboard:** Login, dashboard home (trends, charts, drill-downs), transaction table with filters/edit, review queue, goals page, settings (reminders + upload).
- **Goals system:** 5 goals already entered and tracked — 1 investment goal (₹1.5L/month net investment), 3 monthly expense limits (total < ₹1L, Swiggy food < ₹6K, eating out < ₹10K), 1 annual expense cap (outstation travel < ₹1.2L). Progress auto-computed for expense limits. The dashboard is already goal-centric — the home view leads with "Progress on Goals" and "Reminders," not analytics charts.
- **SQLite database:** Transactions, pipeline runs, processed emails, recurring patterns, goals, reminders.
- **Tests:** 86+ pytest tests, CI with ruff + mypy + coverage gate.

### What doesn't exist yet
- **Asset/holdings data** — no portfolio tracking, no historical positions, no net worth computation, no price feeds.
- **Goal hierarchy** — goals are flat; no parent-child or dependency relationships; no rich properties (funding mode, sequencing, activation conditions).
- **Agent/chat system** — no conversational interface, no agentic reasoning.
- **Simulation engine** — no projection or "what-if" modelling.
- **Personal financial statements** — no P&L, balance sheet, or cash flow statement view; no financial ratios.
- **Layer 3** — no cash flow statement (operating/investing/financing), no liquidity ratios.
- **Multi-user data** — system built for Sashank only; Aditi's banks not yet parsed.

### Architecture facts for Cursor
- Database: SQLite via SQLModel (not Postgres).
- Backend: FastAPI, Python 3.12, Pydantic models.
- Frontend: Next.js 16.2, App Router, TypeScript, shadcn/ui (base-ui), Tailwind v4, Recharts, TanStack Table + Query.
- LLM classification: Gemini Flash Lite via multi-model fallback with caching.
- Infra: Local-first. Single machine, two users.
- Prompt storage: YAML files in `prompts/` directory.

---

## 2 · Three Motivations Driving This Sprint

1. **Learning agentic systems (urgent).** Sashank needs hands-on experience building agents with: tool use / function calling, memory across conversations, evaluation frameworks, multi-step reasoning / planning, and RAG over documents. Career-critical for job transitions.

2. **Revenue path (next 4–8 weeks).** Offer Arth as a managed service to ~10 users from trusted communities. Charge onboarding + subscription. The demo (live website with dummy data, working agent, interactive simulation) attracts first users.

3. **Personal utility.** Sashank and Aditi are merging finances ahead of marriage. System needs to handle joint goals informed by both incomes. Aditi's bank onboarding is deferred to after this sprint.

---

## 3 · What We're Building

### Workstream A: Asset Data Foundation

**Goal:** Build a full portfolio tracking layer — historical positions, real market prices, investment transaction ledger, and liability tracking. This is Layer 1 (Net Worth) of the Arth framework.

#### A1: Unified Holdings Table

One table for all asset types, with nullable columns for instrument-specific fields:

**Common to all holdings:**
- symbol / name
- quantity / units
- asset_class: EQUITY | MUTUAL_FUND | FD | PPF | NPS | SAVINGS | GOLD | SOVEREIGN_GOLD_BOND | REAL_ESTATE | ESOP | OTHER
- account_platform (e.g., "ICICI Direct", "SBI PPF", "HDFC Savings")
- valuation_method: MARKET_PRICE | FIXED_RETURN | MANUAL
- current_value, last_valued_date
- liquidity_class: INSTANT | T_PLUS_1 | T_PLUS_3 | WEEKS | ILLIQUID
- currency (default INR)

**Market-priced instruments (equities, MFs, gold ETFs, NPS, SGBs):**
- average_cost_per_unit, current_price_per_unit
- Nullable for FDs, PPF, real estate.

**Fixed-return instruments (FDs, PPF, bonds):**
- principal_amount, interest_rate, maturity_date, compounding_frequency
- Nullable for equities, MFs.

**Bonds / debt instruments additionally:**
- face_value, coupon_rate, coupon_frequency
- Nullable for everything else.

**Mutual funds additionally:**
- folio_number, fund_type (growth / dividend / IDCW)
- Nullable for non-MFs.

**Why one table:** The total number of holdings will be 30–50 at most. Schema purity matters less than simplicity. Some columns will be null for any given row — that's fine.

**Valuation method determines how current_value is computed:**
- `MARKET_PRICE` — fetch daily closing price from external feed (equities, MFs, gold ETFs, NPS, SGBs).
- `FIXED_RETURN` — compute from principal + rate + tenure formula (FDs, PPF, bonds held to maturity).
- `MANUAL` — user enters/updates value (real estate, ESOPs, collectibles).

**Return computation also branches on asset_class:**
- Equities and MFs: XIRR (Extended Internal Rate of Return) computed from the investment_transactions ledger. Accounts for timing of each buy/sell.
- FDs: stated interest rate — deterministic, no XIRR needed.
- PPF: government-set rate with annual compounding; XIRR optional since contributions vary year-to-year.
- Bonds: yield-to-maturity (YTM) accounting for coupon payments and purchase price vs. face value.
- The system needs a `compute_returns(holding_id)` function that branches on asset_class. The API returns computed return alongside each holding — callers don't need to know which method was used.

#### A2: Investment Transactions Table

Historical buy/sell/dividend ledger — the equivalent of the expense `transactions` table for the investment side:

- date, symbol, transaction_type (BUY / SELL / DIVIDEND / SIP / SWITCH_IN / SWITCH_OUT)
- quantity, price_per_unit, total_amount
- account_platform
- holding_id (FK → holdings) — links this transaction to the specific holding
- bank_transaction_id (nullable FK → transactions) — links to the bank debit/credit that funded this

**The bank reconciliation problem:** When Sashank buys 3 stocks for ₹1L + ₹50K + ₹70K, the bank statement shows one ₹2.2L debit to "ICICI Direct." The `bank_transaction_id` FK links the three investment_transactions to that single bank transaction. On the dashboard, when someone looks at the ₹2.2L outflow, the system can show: "This was 3 purchases: ₹1L INFY, ₹50K TCS, ₹70K HDFC."

This also enables SIP-to-goal tracing: a monthly SIP of ₹10K into Axis Bluechip → these are the 12 purchase transactions → this is the current value → this holding is linked to the "house down payment" goal.

**Dividend linking:** Dividends from stocks/MFs show up as INFLOW in the expense transactions table. Adding a `holding_id` FK on the expense transactions table (nullable) links "this ₹5,000 inflow is a dividend from INFY." This makes total return computable: capital gain + dividends received.

#### A3: Liabilities Table

- name (e.g., "Bike Loan", "Home Loan")
- principal_outstanding, interest_rate, emi_amount, tenure_remaining_months
- emi_start_date, emi_end_date
- liability_type: SECURED_LOAN | UNSECURED_LOAN | REVOLVING_CREDIT | RECURRING_OBLIGATION
- Net worth = Σ holdings.current_value − Σ liabilities.principal_outstanding

#### A4: Holding Statement Parsers

- **ICICI Direct** equity holding statement (CSV/PDF). Standard format — parsing Sashank's data effectively covers anyone on ICICI Direct.
- **ICICI Direct** mutual fund holding statement.
- **Manual entry endpoint** for accounts without parsable statements (PPF, NPS, savings balances, real estate, ESOPs, SGBs).
- New investment transactions should flow in automatically where possible — via email parsing (demat confirmation emails, similar to bank alert scraper) or periodic statement re-import.

#### A5: Daily Price Feed

- Yahoo Finance (`yfinance` Python library) for NSE/BSE equities and mutual fund NAVs.
- **Cadence:** One daily fetch after market close (~6 PM IST). Fetch closing prices for all symbols in the holdings table where valuation_method = MARKET_PRICE.
- **Backfill:** If server was off or a fetch was missed, the next run backfills missing days from Yahoo Finance's historical API.
- **Storage:** `prices` table: symbol, date, close_price, source. One row per symbol per trading day.
- **Historical net worth:** With holdings + historical prices, the system can compute net worth on any past date → enables net worth trend charts.

#### A6: New API Endpoints

- `GET /api/holdings` — list with filters (asset_class, account_platform, liquidity_class)
- `GET /api/holdings/summary` — net worth, asset allocation breakdown, concentration metrics
- `GET /api/holdings/history` — net worth over time (daily/weekly/monthly data points)
- `GET /api/holdings/{id}` — single holding with computed returns (XIRR or appropriate method)
- `PATCH /api/holdings/{id}` — manual value update
- `GET /api/investment-transactions` — historical ledger with filters
- `POST /api/prices/refresh` — trigger price update for all held symbols
- `GET /api/liabilities` — list all liabilities
- `GET /api/liabilities/summary` — total outstanding, total EMI burden, debt-to-asset ratio

---

### Workstream B: Goal Hierarchy & Properties

**Goal:** Transform the flat goals list into a rich, hierarchical goal system with causal links, sequencing logic, and properties that enable simulation.

#### B1: Extend Goals Data Model

**Add to existing `goals` table:**

- `time_horizon`: MONTHLY | QUARTERLY | ANNUAL | MULTI_YEAR | DECADE
- `tier`: VISION | STRATEGY | TACTIC | OPERATIONAL
- `funding_mode`: ACCUMULATION | CONSTRAINT | EVENT | MAINTENANCE
  - ACCUMULATION: building a pot over time (down payment, emergency fund, corpus)
  - CONSTRAINT: keeping something below a threshold (expenses < ₹1L/month)
  - EVENT: one-time financial event, binary done/not-done (buy insurance, pay for wedding)
  - MAINTENANCE: condition that must remain continuously true (emergency fund stays at 6 months)
- `activation_status`: PENDING | ACTIVE | COMPLETED | PAUSED
- `activation_condition`: nullable text/JSON — what triggers this goal to go active (e.g., "goal:S4:completed AND goal:S6:completed" or "event:employed" or "event:child_born"). Goals with null activation_condition are active immediately.
- `monthly_allocation`: float — current monthly allocation from the surplus pool
- `allocation_priority`: int — when surplus is limited, which goals get funded first (1 = highest priority)
- `interruptible`: bool — can this goal be paused without catastrophic impact
- `sensitivity_to_returns`: LOW | MEDIUM | HIGH — how much market performance affects this goal

**New `goal_links` table:**

- id (PK)
- parent_goal_id → FK to goals
- child_goal_id → FK to goals
- link_type: DECOMPOSES_INTO | DEPENDS_ON | CONTRIBUTES_TO
- description — optional text explaining the relationship
- contribution_amount — optional float, for CONTRIBUTES_TO links

**Link types:**
- **DECOMPOSES_INTO:** Parent achieved when all children achieved. "Buy house" = "save down payment" + "qualify for loan."
- **DEPENDS_ON:** Parent requires child as a precondition. "Qualify for loan" depends on "maintain cash flow for EMI." Child isn't part of parent; it's a gate.
- **CONTRIBUTES_TO:** Child's progress feeds parent with measurable flow. "Keep expenses under ₹1L" contributes to "Save ₹1.5L/month" which contributes to "₹1Cr down payment."

#### B2: Seed the Real Goal Pyramid

The full pyramid from the financial goals discussion should be entered:

**Vision (4 goals):** Lifestyle freedom (₹5L/month passive by age 45-48), family home in Bangalore (3-4BHK, ₹3-4.5Cr), family catastrophe protection, child fund.

**Strategy (7 goals):** Build investment engine (₹2-2.5Cr in 5yr), house down payment (₹20-30L), full insurance coverage, emergency fund (₹6-8L), re-enter workforce at ₹40L+, fund wedding (₹10-15L), grow indie revenue to ₹1-1.5L/month.

**Tactics (13 goals):** Annual investment targets, emergency fund completion, expense caps, tax optimization, wedding fund, child fund SIP, house fund allocation, indie revenue milestones. Include the ₹6L/year travel goal (₹5L domestic + ₹1L international).

**Operations (10 goals):** Monthly expense limits, SIP execution, house fund monthly allocation, emergency fund monthly deposits, wedding savings, monthly financial review, job search actions, health insurance purchase.

All goals should have their goal_links entered to form the complete causal map (the relationship table from the financial goals document).

#### B3: Goal API Endpoints

- `GET /api/goals/tree` — full goal graph with links, suitable for hierarchy rendering
- `GET /api/goals/{id}/ancestors` — trace upward: what higher goals does this feed
- `GET /api/goals/{id}/descendants` — trace downward: what operational goals support this
- `POST /api/goal-links` — create a link
- `DELETE /api/goal-links/{id}` — remove a link
- `GET /api/goals/{id}/impact` — given a change in this goal, which other goals are affected
- `GET /api/goals/allocation` — current monthly surplus allocation across all active goals

---

### Workstream C: Multi-Agent System

**Goal:** Build a financial planning agent using an orchestrator + specialist architecture. CLI-first, then dashboard.

#### C1: Architecture

**Orchestrator (the "brain"):**
- Receives user's question, classifies intent, routes to specialist(s)
- Coordinates between specialists for cross-cutting questions
- Synthesizes specialist outputs into coherent response
- Runs on the most capable model (Opus / Sonnet / GPT-4o — benchmark to decide)
- Maintains conversation state and memory
- **Must always route to a specialist. No fallback execution.** If no specialist fits, the orchestrator tells the user honestly that the question is outside current system capability and explains what data/capability would be needed. This keeps the orchestrator as a pure router, avoids expensive unnecessary processing, and surfaces gaps clearly.

**Specialists:**

| Specialist | Scope | Tools | Model tier |
|---|---|---|---|
| **Spending Analyst** | Layer 2 — expenses, income, savings rate, categories | get_spending_summary, get_spending_by_category, get_monthly_trend, get_expense_trend, get_category_trend, get_top_expenses, get_transactions, get_top_counterparties | Fast/cheap |
| **Portfolio Analyst** | Layer 1 — holdings, net worth, allocation, concentration, returns | get_net_worth, get_holdings_breakdown, get_holdings_history, get_investment_transactions, get_investment_trend, get_holding_returns | Fast/cheap |
| **Goal Tracker** | Goals — progress, hierarchy, impact, sequencing, allocation | get_goals, get_goal_tree, get_goal_progress, get_goal_ancestors, get_goal_descendants, get_goal_impact, get_goal_allocation | Fast/cheap |
| **Simulation Runner** | What-if — projections, parameter sensitivity, scenario comparison | run_projection, compare_scenarios, project_goal_cascade | Fast/cheap (mostly deterministic math; LLM interprets results) |

**Cross-cutting example:** "Am I on track for my house goal?" → Orchestrator calls Goal Tracker (get the goal and its dependencies) + Portfolio Analyst (current net worth, investment rate) + Spending Analyst (current savings rate) → synthesizes: "At your current savings rate of 42% and 12% equity returns, you'll hit your down payment target by 2034. Accelerating to 2032 requires either ₹15K more monthly investment or 15% returns."

#### C2: Agent Tools

Tools wrap existing FastAPI endpoints. Don't bypass the API — it encodes business logic.

**Spending Analyst tools** map to `/api/metrics/*` and `/api/transactions`.
**Portfolio Analyst tools** map to `/api/holdings/*`, `/api/investment-transactions`, `/api/liabilities/*`.
**Goal Tracker tools** map to `/api/goals/*` and `/api/goal-links/*`.
**Simulation Runner tools** map to `/api/simulate/*` (Workstream D).
**Financial Statements tools** map to `/api/statements/*` (Workstream E).

*(Detailed tool-to-endpoint mapping exists in v2 of this doc and remains valid.)*

#### C3: CLI Agent

- REPL interface (interactive terminal: type question → get answer → repeat).
- Debug mode showing: which specialist(s) chosen, tool calls, raw data, synthesis reasoning.
- Conversation history within session.
- Multi-LLM backend abstraction — swap between Claude, Gemini, GPT-4o for any agent role.

#### C4: Memory System

**Conversation memory (within session):** Message history with sliding window or summarization.

**Cross-session memory:** After each conversation, generate a summary of decisions, insights, action items. Store as retrievable documents. On new conversation, retrieve recent + relevant summaries.

**User profile:** Standing facts (name, age, risk tolerance, preferences, which accounts are joint). Structured JSON/YAML in orchestrator's system prompt. Manually maintained initially.

#### C5: RAG System

Small corpus (< 50 docs): goals framework, layer framework, past conversation summaries, financial planning notes. Lightweight embedding + cosine similarity. RAG enhances system prompt, doesn't replace core knowledge.

#### C6: Evaluation Framework

25–40 questions across categories:

| Category | Count | Tests |
|---|---|---|
| Factual lookup | 10–12 | Single-tool accuracy |
| Cross-layer reasoning | 8–10 | Multi-specialist coordination |
| Advisory / subjective | 5–8 | Goal-awareness, actionability |
| Simulation / what-if | 4–6 | Projection accuracy |
| Conversational | 4–6 | Memory, multi-turn coherence |
| Edge cases | 3–5 | Graceful handling of unknowns |

Each question defines: required specialists, required tool calls, required reasoning elements, quality rubric. Run across LLM combinations. Track results for iteration and portfolio demonstration.

---

### Workstream D: Simulation Engine

**Goal:** Deterministic projection/simulation functions usable by both the agent and the dashboard.

#### D1: Core Simulation Functions

All pure math — no LLM involved.

**`project_savings_goal(current_balance, monthly_contribution, annual_return_rate, target_amount)`**
→ months_to_target, projected_date, month_by_month_trajectory

**`project_expense_impact(current_savings_rate, expense_change_amount, affected_goals[])`**
→ new_savings_rate, impact_on_each_goal (months gained/lost)

**`project_net_worth(current_holdings, monthly_investment, annual_return_rate, months_forward)`**
→ projected_net_worth_by_month

**`project_loan_feasibility(loan_amount, interest_rate, tenure, current_income, current_expenses)`**
→ emi_amount, debt_service_coverage_ratio, max_feasible_loan

**`compute_xirr(cash_flows: list[date, amount])`**
→ annualized return rate

**`project_goal_cascade(goal_id, parameter_changes)`**
→ Traces through goal_links to compute impact on all connected goals.

**`allocate_surplus(monthly_surplus, active_goals_with_priorities)`**
→ Allocates surplus across competing goals by priority, respecting activation conditions. This is the core sequencing logic — higher-priority goals get funded first, remaining surplus flows to lower-priority goals.

**`compare_scenarios(scenario_a_params, scenario_b_params)`**
→ Side-by-side comparison of outcomes for each goal under two parameter sets.

#### D2: Simulation API Endpoints

- `POST /api/simulate/project` — forward projection with given parameters
- `POST /api/simulate/compare` — compare two scenarios side by side
- `POST /api/simulate/goal-impact` — parameter change → impact on all goals in hierarchy
- `POST /api/simulate/allocate` — given a surplus and goal set, show optimal allocation over time

---

### Workstream E: Personal Financial Statements & Ratios

**Goal:** Present Sashank's finances in the same framework used to analyze companies — P&L, balance sheet, cash flow statement, and financial ratios. This is a presentation layer on data already being built, not a new data layer.

#### E1: Personal P&L Statement

Generated per period (monthly / quarterly / annual):

| Line item | Source |
|---|---|
| Total income (salary, bonuses, dividends, rental, side hustle) | Transactions (INFLOW, filtered by type) |
| Less: Taxes paid | Transactions (tax-related outflows) |
| **Gross income** | Computed |
| Less: Fixed expenses (rent, EMIs, insurance premiums) | Transactions (fixed category outflows) |
| Less: Variable essentials (groceries, utilities) | Transactions (essential variable outflows) |
| Less: Discretionary (dining, hobbies, travel) | Transactions (discretionary outflows) |
| **Operating surplus (EBITDA equivalent)** | Computed |
| Less: Asset depreciation (bike, electronics — optional) | Computed from asset purchase dates |
| Less: Loan interest component | Computed from liabilities table |
| **Net surplus (PAT equivalent)** | What actually gets added to net worth |

#### E2: Personal Balance Sheet

Point-in-time snapshot:

| Section | Source |
|---|---|
| **Current assets:** Cash, savings accounts, liquid MFs | Holdings where liquidity_class = INSTANT or T_PLUS_1 |
| **Non-current assets:** Equities, MFs, FDs, PPF, NPS, real estate, gold | Holdings where liquidity_class > T_PLUS_1 |
| **Current liabilities:** CC dues, upcoming EMIs, tax payable | Liabilities (short-term) |
| **Non-current liabilities:** Home loan, education loan, car loan | Liabilities (long-term) |
| **Net worth (equity)** | Total assets − Total liabilities |

#### E3: Personal Cash Flow Statement

Per period:

| Section | Source |
|---|---|
| **Operating cash flow:** Income minus expenses | Transactions (Layer 2 data) |
| **Investing cash flow:** Asset purchases minus sales | Investment_transactions table |
| **Financing cash flow:** Loan drawdowns minus principal repayments | Liabilities + transactions |
| **Net cash flow** | Change in cash/bank balance for period |

This also delivers **Layer 3 (Cash Flow & Liquidity)** — operating/investing/financing flows, liquidity ratios, and seasonality are all computable from the data being built in this sprint.

#### E4: Personal Financial Ratios

**Profitability ratios:**
- Savings rate (PAT margin equivalent) — already computed
- Gross margin: (Income − Taxes) / Income
- Return on Net Worth: net worth growth / average net worth (personal ROE)
- Investment rate: monthly investment / monthly income

**Leverage ratios:**
- Debt to Equity: total liabilities / net worth
- Interest Coverage: monthly income / monthly interest obligations
- Debt to Asset: total liabilities / total assets
- EMI to Income: total EMIs / monthly income

**Operating ratios:**
- Expense efficiency: essential expenses / total expenses (needs vs wants)
- Asset turnover: total income / total assets

**Liquidity ratios (Layer 3):**
- Cash runway: liquid assets / average monthly core expenses
- Liquidity ladder: time-to-cash breakdown (instant, T+1, T+3, weeks, illiquid)
- Quick ratio: liquid assets / current liabilities

#### E5: API Endpoints

- `GET /api/statements/pnl` — P&L for a given period
- `GET /api/statements/balance-sheet` — balance sheet at a point in time
- `GET /api/statements/cash-flow` — cash flow statement for a period
- `GET /api/statements/ratios` — all computed financial ratios
- `GET /api/statements/ratios/trend` — ratios over time (monthly/quarterly)

These endpoints serve both the dashboard (dedicated pages) and the agent (specialists can call them for analysis).

---

### Workstream F: Dashboard Enhancements

**Design philosophy:** The dashboard is goal-centric, not metric-centric. The home view leads with goal progress and reminders — this is already the case and should remain so. Metrics, charts, and financial statements are available as deep-dive pages, not the primary view.

#### F1: Chat Interface

New route: `/chat`

- Backend endpoint (or WebSocket) accepting user message + conversation history, running the orchestrator, streaming the response.
- Collapsible "thinking" section showing which specialists were called, what tools they used, what data they found. Builds trust; great for demo.
- Markdown rendering in responses (tables, bold numbers).
- Conversation history persists across page refreshes.

#### F2: Asset / Portfolio Page

New route: `/portfolio` (or `/assets`)

A dedicated page — not a section on the home dashboard. The home dashboard remains goal-centric.

- Holdings table: name, quantity, current value, cost basis, gain/loss (₹ and %), weight in portfolio, XIRR/return
- Asset allocation breakdown (by asset_class, by liquidity_class, by account)
- Concentration indicators (% in employer equity, % in single largest holding)
- Net worth trend chart (uses historical prices + holdings)
- Investment transaction history with bank reconciliation (show which bank debit funded which purchases)

#### F3: Financial Statements Pages

New route: `/statements`

- P&L, balance sheet, cash flow statement — formatted like corporate financial statements
- Financial ratios dashboard with trend lines
- Liquidity ladder visualization
- Period selector (monthly / quarterly / annual / custom)

#### F4: Simulation Slider UI

On the goals page or as a dedicated route:

- Adjustable sliders: monthly savings, expected return rate, expense growth, income growth, one-off events (wedding cost, bonus, house purchase)
- Real-time recalculation as sliders move — projected timeline for each goal, with status changes (on-track → at-risk) cascading through the goal hierarchy
- Allocation visualization: shows how monthly surplus is distributed across competing goals over time, and how that distribution shifts when parameters change
- Uses the same simulation API endpoints that the agent uses. Same math, two interfaces.

---

### Workstream G: Demo Site

**Same repo, different deployment configuration.**

#### G1: Demo Mode

- Environment variable: `DEMO_MODE=true`
- Seeds database with synthetic data on startup
- Disables write operations (no editing, no pipeline runs, no scraper)
- Shows banner: "Demo with sample data"
- Frontend and backend code identical to production. Only data and write permissions differ.

#### G2: Synthetic Data

Realistic dummy data for a fictional Indian professional:
- 6–12 months of classified transactions (Indian banks, INR, real-looking merchants)
- Holdings portfolio (stocks, MFs, FD, PPF, SGBs) with price history
- Liabilities (bike loan, term insurance obligation)
- Goal hierarchy spanning all four tiers, with goals in various states (on-track, at-risk, completed, pending activation)
- Enough variety to showcase: expense tracking, portfolio view, financial statements, goal progress, agent Q&A, simulation sliders

#### G3: Deployment

- Production: runs locally, `DEMO_MODE=false`, real data.
- Demo: deployed to Fly.io / Render / Railway / Vercel, `DEMO_MODE=true`, synthetic data.
- Same Docker image, different env vars. Code changes push to both automatically.

#### G4: Landing & CTA

- Landing overlay explaining what Arth is.
- No login required — demo is read-only.
- CTA: "Want this for your finances? Join the waitlist" → collect email/WhatsApp.

---

## 4 · What We're NOT Building This Sprint

- **Aditi's bank parsers** — she's the first "multi-user" test after the sprint.
- **Portfolio advisor / market research agent** (market pulse, sector trends, buy/sell) — second specialist that builds on the same orchestrator. Comes after.
- **Layers 4, 5** (risk protection, tax optimization) — future sprints. (Layer 3 is substantially delivered via financial statements and ratios.)
- **Intraday price data** — daily closing prices are sufficient.
- **Mobile app, push notifications, WhatsApp/Telegram integration.**
- **Multi-tenant architecture** — first 10 users each get their own deployed instance.
- **Ad-hoc agent creation by orchestrator** — the orchestrator routes to defined specialists only; no dynamic agent spinning.

---

## 5 · Security & Privacy

This sprint introduces new attack surfaces: LLM API keys, external market data APIs, a publicly accessible demo site, and agent conversation history containing detailed financial data. Security needs to be addressed per workstream, not as a separate hardening phase.

### What exists today
- **Auth:** httpOnly session cookie (`arth_session`) set by FastAPI after login. Credentials (`AUTH_USERNAME`, `AUTH_PASSWORD`, `AUTH_SECRET_KEY`) stored in `.env`. Single household login — not multi-tenant.
- **CORS:** Restricted to localhost origins by default; `CORS_EXTRA_ORIGINS` for Cloudflare Tunnel or other dev setups.
- **Database:** SQLite file on disk. No encryption at rest. No column-level PII encryption.
- **Secrets:** `.env` file with API keys (LLM providers, Gmail OAuth). Gitignored.
- **Gmail OAuth:** Token stored locally after first-run consent flow. Scoped to read-only Gmail access.

### What this sprint adds and the security implications

**Holdings & financial data (Workstream A):**
- The holdings table contains the most sensitive data in the system — exact portfolio positions, account platforms, asset values. If the SQLite file is compromised, everything is exposed.
- **Requirement:** Evaluate SQLCipher (encrypted SQLite) or at minimum ensure the data directory has restricted file permissions. Column-level encryption on PII fields (account numbers, folio numbers) using a key from `.env`. This is the "cheapest viable solution" from the original PRD — implement it now that the data is genuinely sensitive.
- **Price feed API keys:** Yahoo Finance via `yfinance` doesn't require an API key (it scrapes). If a paid API is used later, keys go in `.env` and are never logged.

**LLM API keys (Workstream C):**
- The agent system will call multiple LLM providers (Anthropic, Google, OpenAI). Each requires API keys.
- **Requirement:** All API keys in `.env`, never in code or logs. The multi-LLM abstraction layer should sanitize error responses so that API keys aren't leaked in stack traces or debug output. Rate limiting / spend caps on LLM API usage to prevent runaway costs from agent loops.

**Agent conversation history (Workstream C):**
- Conversations will contain raw financial data — account balances, transaction details, goal targets, net worth figures. If stored (for memory/cross-session), this is highly sensitive.
- **Requirement:** Conversation history stored locally (not in any third-party service). Memory summaries should be abstractive, not verbatim — "user discussed reducing food spending" not "user spends ₹32,400/month on food at Swiggy." Consider whether conversation logs should be encrypted at rest.

**Demo site (Workstream G):**
- A publicly accessible deployment with synthetic data. No real financial data. But the same codebase as production.
- **Requirement:** `DEMO_MODE=true` must disable ALL write operations — not just UI buttons, but API-level enforcement. No path from the demo site to real data. Demo database is seeded fresh on deploy, never connected to production data. Auth is disabled or uses a public demo account — no real credentials exposed.
- **Requirement:** The demo site should not expose API endpoints that reveal system internals (pipeline runs, scraper status, OAuth endpoints). Either disable these routes in demo mode or return mock data.

**Gmail scraper (existing, but relevant):**
- OAuth tokens grant read access to the inbox. If the token file is compromised, an attacker can read bank alert emails.
- **Requirement:** Token file should have restricted file permissions (600). Consider adding a check that the token hasn't been accessed by unexpected processes.

### Security principles for this sprint

1. **Secrets never in code or logs.** All API keys, auth credentials, and OAuth tokens in `.env` or equivalent. Debug/verbose modes must sanitize output — no API keys, no raw account numbers in agent debug traces.
2. **Demo mode is a hard boundary.** `DEMO_MODE=true` enforces read-only at the API layer, not just the UI. No writes, no real data access, no sensitive endpoints exposed.
3. **Encrypt what matters most.** At minimum: column-level encryption on PII fields in the holdings table (account numbers, folio numbers). Evaluate full-database encryption (SQLCipher) as a low-effort upgrade.
4. **LLM spend guardrails.** Set per-session and per-day token/cost limits for LLM API calls. An agent stuck in a loop should hit a ceiling before it burns through credits.
5. **Conversation data is financial data.** Treat stored conversation history with the same sensitivity as the database itself. Local storage only, no third-party logging, consider encryption.
6. **No DR SLA, but have a backup.** The system runs on a single laptop with SQLite. A weekly automated backup of the database file (even just a cron copying `arth.db` to a dated file) prevents catastrophic data loss. Accept ≤ 1 week RPO (recovery point objective) for now.

---

## 6 · Technical Principles

### Data layer
1. **One holdings table, branching logic.** Unified table with nullable instrument-specific columns. Valuation method and return computation branch on asset_class.
2. **Investment_transactions is the portfolio's transaction ledger.** Every buy, sell, SIP, dividend. With bank_transaction_id FK for reconciliation.
3. **Prices are infrastructure.** Daily cron, backfill on missed days, Yahoo Finance. The features it enables (trends, XIRR, simulation accuracy) are what users see.
4. **Goal links create a directed graph.** A goal can have multiple parents. The graph encodes *why* a goal exists. Activation conditions encode *when* it kicks in.
5. **Financial statements are a presentation layer.** P&L, balance sheet, cash flow, and ratios are computations over existing data, not new data.

### Agent system
6. **The API is the truth layer.** Agents call FastAPI endpoints, not raw SQL.
7. **The orchestrator is a pure router.** It classifies, routes, and synthesizes. It never executes analytical work itself. If no specialist fits, it says so honestly.
8. **Show your work.** Cite specific numbers. "₹32,400 on food, 8% above your ₹30K target" — not "spending seems high."
9. **Know what you don't know.** Missing data → say so, explain what's needed.
10. **Memory is continuity.** Make the next conversation feel like a continuation.
11. **Evals are first-class.** As important as the agent itself.

### Simulation engine
12. **Simulation is deterministic math.** The engine computes; the agent interprets.
13. **Same math, two interfaces.** Agent (conversational what-if) and dashboard (sliders). One computation layer, two presentation layers.
14. **Surplus allocation is the core loop.** The simulation doesn't project goals in isolation — it allocates a shared monthly surplus across competing goals by priority, with goals entering and exiting based on activation conditions.

### Dashboard
15. **Goal-centric, not metric-centric.** The home view is about goals and reminders. Metrics, portfolio, and financial statements are deep-dive pages.

---

## 7 · Success Criteria

By end of sprint:

1. **Data:** Holdings populated with real portfolio. Investment_transactions loaded. Daily price feed with backfill. Liabilities entered. Net worth computable historically. Dividend linking working.

2. **Goals:** Full four-tier pyramid entered (V1–V4, S1–S7, T1–T13, O1–O10). goal_links table with all causal relationships. Goal properties (funding_mode, activation_condition, allocation_priority, etc.) populated.

3. **Agent (CLI):** Multi-agent system with orchestrator + 4 specialists. Answers factual, cross-layer, advisory, and what-if questions. Memory across conversations. RAG. Eval suite of 25+ questions across LLM combinations.

4. **Agent (Dashboard):** Chat page with reasoning transparency and conversation persistence.

5. **Simulation:** Deterministic engine with surplus allocation logic, goal cascade, scenario comparison. API endpoints serving both agent and dashboard.

6. **Dashboard:** Portfolio page, financial statements pages (P&L, balance sheet, cash flow, ratios), simulation slider UI. Home view remains goal-centric.

7. **Demo:** Public site with synthetic data. Everything working. Waitlist CTA.

8. **Learning:** Sashank can articulate tool use, memory, RAG, multi-step reasoning, evals, and multi-agent orchestration with concrete examples.

---

## 8 · Reference: Layer Status After Sprint

| Layer | Coverage |
|---|---|
| 0 — Governance | Partially built. Agent + simulation add new surfaces. |
| 1 — Net Worth | **Fully built.** Portfolio tracking, historical prices, returns, concentration metrics. |
| 2 — Earnings & Spending | **Fully built.** Agent adds conversational access. |
| 3 — Cash Flow & Liquidity | **Substantially built.** Operating/investing/financing flows via financial statements. Liquidity ratios via holdings + liquidity_class. Seasonality from historical transaction data. |
| 4 — Risk | Future sprint. (Emergency fund and insurance goals exist but risk analysis layer is not built.) |
| 5 — Tax & Legal | Future sprint. |

---

## 9 · Reference Documents

**Keep in this project:**
- `goals_framework.md` — Section 1 (vision of goals as missing axis) remains the north star.
- `Arth___Layers.pdf` — Layer framework definition. Domain reference.
- `Arth__Questions_to_Layers.pdf` — Question catalogue per layer and cross-layer. Domain reference.
- The financial goals pyramid PDFs — the full goal discussion and resulting pyramid document.
- Three README files — update these as the codebase evolves.

**Replace:**
- `arth_prd_v_1.md` — this guideline document replaces it.

---

*This is the final planning document for the sprint. Take it to Cursor. Build. Come back here when you've completed a meaningful chunk to plan the next phase.*
