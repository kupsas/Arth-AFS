# Raw HDFC Statement vs GSheet_Transactions — Difference Notes

How the **raw HDFC account statement** (SSOT) differs from the **GSheet_Transactions** CSV (enriched sheet you maintained). The raw file in repo is `Acct_Statement_XXXXXXXX3703_11012026.txt` (text export); the exact column layout is documented in the prior ChatGPT chat and is summarized below.

---

## 1. Raw HDFC statement (source of truth)

**Columns (from prior chat):**

| Column            | Meaning                          | Example / notes                          |
|------------------|-----------------------------------|------------------------------------------|
| Date             | Transaction date                  | 01/02/25                                 |
| Narration        | Full bank description             | UPI-AMAZON INDIA-AMAZON@RAPL-...          |
| Chq./Ref.No.     | Cheque or reference number        | 0000503322666760                          |
| Value Dt         | Value date                        | 01/02/25 (often same as Date)            |
| Withdrawal Amt.  | Debit amount                      | 1099 (empty for credits)                 |
| Deposit Amt.     | Credit amount                     | 127557 (empty for debits)                |
| Closing Balance  | Balance after transaction         | 135785.76                                |

**Characteristics:**

- One row per bank row; no IDs, no classification.
- No normalized counterparty, no txn_type, no channel, no category.
- Amount is split into two columns (Withdrawal vs Deposit); direction is implicit.
- Narration is verbose (UPI strings, NEFT/IMPS/ACH text, refs, etc.).

---

## 2. GSheet_Transactions (enriched layer)

**Columns present in CSV:**

| Column                   | Source / meaning |
|--------------------------|-------------------|
| txn_id                   | **Added.** Sequential ID (e.g. T_00000001). |
| txn_date                 | **From raw.** Date normalized (e.g. DD-MM-YY format in CSV). |
| account_id               | **Added.** Constant for this file (50100509403703 — HDFC account). |
| direction                | **Derived.** INFLOW or OUTFLOW from Withdrawal/Deposit. |
| amount                   | **From raw.** Single positive number from Withdrawal or Deposit. |
| currency                 | **Added.** INR for all. |
| txn_type                 | **Derived.** From Narration via rules/AI (e.g. UPI_EXPENSE, CARD_PAYMENT). |
| channel                  | **Derived.** UPI, BANK, CARD, BROKER from Narration. |
| upi_type                 | **Derived.** P2M, P2P, NA (when channel = UPI). |
| counterparty            | **Derived.** Normalized merchant/person/institution from Narration (AI-assisted). |
| counterparty_category    | **Derived.** Theme/category (e.g. Food & Dining, Self Transfer) from txn_type + counterparty. |
| txn_type + counterparty  | **Derived.** Concatenation used as input for category AI prompt. |
| linked_asset             | **Added.** Empty in current data; for future use. |
| linked_txn_id            | **Added.** Empty in current data; for pairing events. |
| raw_description         | **From raw.** Same as Narration (preserved verbatim). |
| source_statement         | **Added.** Empty in CSV; would identify statement source. |
| notes                    | **Added.** Manual notes; empty in most rows. |

---

## 3. Main differences (summary)

| Aspect              | Raw HDFC statement              | GSheet_Transactions                          |
|---------------------|----------------------------------|----------------------------------------------|
| **Row identity**    | No ID                            | Stable `txn_id` (T_00000001, …)              |
| **Amount**          | Two columns (Withdrawal, Deposit)| Single `amount` + `direction`                |
| **Date**            | Date (and Value Dt)              | Single `txn_date` (format may differ)         |
| **Description**     | Narration only                   | Same in `raw_description` + derived fields   |
| **Classification**  | None                             | `txn_type`, `channel`, `upi_type`            |
| **Counterparty**    | None                             | Normalized `counterparty` (AI-assisted)      |
| **Category**        | None                             | `counterparty_category` (AI-assisted)        |
| **Account**         | Implicit (one statement)         | Explicit `account_id`                         |
| **Currency**        | Implicit INR                     | Explicit `currency`                           |
| **Balance**         | Closing balance per row          | Not carried into GSheet                       |
| **Ref no.**         | Chq./Ref.No.                     | Not carried (could be in notes if needed)     |

---

## 4. Derivation rules (from raw → GSheet)

- **direction:** If raw has Withdrawal Amt. → OUTFLOW; if Deposit Amt. → INFLOW.
- **amount:** Whichever of Withdrawal/Deposit is non-empty, as positive number.
- **txn_date:** From Date (and in GSheet often stored as DD-MM-YY).
- **raw_description:** Copy of Narration; never edited.
- **txn_type, channel, upi_type, counterparty, counterparty_category:** From Narration (and counterparty/category from AI prompts; see `GSheet_prompts_used.md`).

---

## 5. What’s not in the raw file

- No `txn_id`, no `account_id`, no `currency`, no `source_statement`, no `notes`.
- No classification columns; all of those are added in the sheet/CSV.

---

## 6. What’s not in the GSheet (dropped from raw)

- **Closing Balance** — not imported into the transactions table (could be added elsewhere for reconciliation).
- **Chq./Ref.No.** — not a column in GSheet (could be stored in `notes` if needed).
- **Value Dt** — not used; only transaction date is kept.

---

## 7. Data scope

- **Raw:** Single account, HDFC; FY 2025–26 (and possibly into 2026 from filename).
- **GSheet_Transactions:** Same account (`50100509403703`), same period; ~650 rows; one row per transaction with enriched classification and category.

---

*Raw statement: `docs/personal-data/Acct_Statement_XXXXXXXX3703_11012026.txt`. Enriched export: `docs/personal-data/GSheet_Transactions.csv`. Prompts used for AI columns: `docs/GSheet_prompts_used.md`.*
