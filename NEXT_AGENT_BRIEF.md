# Next Agent Brief: Prompt Improvement for Transaction Classification

**Goal:** Push counterparty and counterparty_category accuracy from ~47%/60% toward 85%+ on the full 648-row HDFC savings dataset, using gemini-3.1-flash-lite as the primary model.

**Delete this file when the work is done.**

---

## Current State

The pipeline works end-to-end. Rules classify channel (100%), most txn_types (91%), and basic upi_types. The LLM fills remaining fields. The weak spots are **counterparty naming** (47%) and **counterparty_category** (60%).

- **Model:** gemini-3.1-flash-lite (single-pass, all fields in one call)
- **Prompt:** `pipeline/prompts.py` -> `batch_classify_prompt()`
- **Ground truth:** `docs/personal-data/GSheet_Transactions.csv`
- **Validator:** `python3 -m pipeline.run --validate` compares against ground truth
- **Benchmark tool:** `docs/evaluations/llm-benchmark-2026-03/benchmark.py` can re-run the 20-transaction benchmark to measure prompt changes on a small set before running the full 648

---

## The Five Biggest Accuracy Problems (in order of impact)

### 1. Uber/Ola Driver Names (26% of all transactions)

171 of 648 transactions are UPI payments to cab drivers. The narration shows a person's name (e.g., "CHANDRASHEKAR G C") but the correct classification is counterparty=Uber, category=Transport & Fuel.

**Pattern:** UPI + OUTFLOW + person name (no merchant keywords) + amount between ~80-1200 + usually non-round numbers.

The current prompt has one example of this. It needs 3-5 more examples and an explicit rule like: "P2P payments of 80-1200 INR to unknown persons with no merchant keywords in the UPI ID are very likely Uber/Ola rides in Bangalore — classify as counterparty=Uber, category=Transport & Fuel."

The tricky part: not ALL small P2P payments are cab rides. Some are genuinely "Friends and Family." But the amount range + non-round amount + unknown person is a strong signal.

### 2. Counterparty Naming Inconsistency

The validator's counterparty match rate (47%) is artificially low because of naming mismatches:
- Pipeline says "Reliance Jio", ground truth says "Reliance Jio Infocom"
- Pipeline says "HDFC Bank", ground truth says "HDFC Credit Card"
- Pipeline says "Tide Platform" for salary, ground truth says "Sashank Sai Kuppa"
- Pipeline says "Sterling", ground truth says "Sterling Rent"

**Two fixes needed:**
1. **Validator:** Use fuzzy/substring matching for counterparty (one contains the other = match). Currently it's doing `g in e or e in g` but some cases still fail.
2. **Prompt:** Add guidance for known counterparties: "For salary (TIDEPLATFO), counterparty = the employee name (from narration), not the payroll platform." "For IB BILLPAY, counterparty = HDFC Credit Card, not HDFC Bank."

### 3. Category Confusion Pairs

Specific category pairs that the model frequently confuses:
- **Friends and Family vs Transport & Fuel** — the Uber driver problem above
- **Utilities & Internet vs Mobile, OTT & Subscriptions** — Jio/Airtel classified as subscriptions instead of utilities
- **Shopping & E-commerce vs Entertainment & Events** — venues like Nexus mall classified as shopping instead of entertainment
- **Shopping & E-commerce vs Miscellaneous** — small BharatPe/PayTM merchants that are actually local shops

### 4. Inflow Classification Edge Cases

- Person paying user for event tickets (e.g., "ED SHEERAN CONCERT" in the narration) — should be Entertainment & Events, not Friends and Family
- Family transfers via RDA (remittance) — ground truth says "Friends and Family" but model sometimes says "Salary & Income"
- Tax refunds — ground truth says "Fees, Charges & Interest" but model says "Salary & Income"

### 5. Same Person, Different Categories

Ashlesha Naokarkar appears in the dataset as both Rent & Housing (TPT rent payment) and Friends & Family (UPI transfer). The narration context is the distinguishing signal:
- "STERLING 5042 RENT-ASHLESHA NAOKARKAR" -> Rent & Housing
- "UPI-ASHLESHA NAOKARKAR-...-PAYMENT FROM PHONE" -> Friends and Family

---

## Suggested Approach

### Phase 1: Quick Wins (just prompt changes)
1. Add 5+ Uber driver few-shot examples to the prompt, with explicit heuristic rule
2. Add specific counterparty naming guidance for known patterns (salary, bill pay, rent)
3. Add more category disambiguation examples for the confusion pairs above
4. Run `python3 -m pipeline.run --validate` after each change to measure impact

### Phase 2: Validator Improvements
1. Relax counterparty matching to fuzzy/substring
2. This alone will boost reported accuracy from 47% to probably 60-70% without changing any prompt

### Phase 3: Harder Problems
1. Consider a small "pattern rules" addition to `rules_classifier.py` for the Uber pattern (UPI + person name + amount 80-1200 + non-round = auto-classify as Uber before it even hits the LLM)
2. Investigate whether batch size affects quality (currently 15 per batch — would smaller batches of 10 help?)

---

## How to Measure Progress

```bash
# Quick test on the 20-transaction benchmark fixture (fast, cheap)
cd /path/to/Arth
python3 docs/evaluations/llm-benchmark-2026-03/benchmark.py --model gemini-3.1-flash-lite --strategy single

# Full run on 648 transactions (takes ~12s)
python3 -m pipeline.run --validate
```

The validation report shows per-field accuracy. Focus on counterparty and counterparty_category percentages.

**Important:** Clear the LLM cache (`data/.llm_cache/classify_cache.json`) before re-running after prompt changes, or cached results from the old prompt will be served.

---

## Files to Edit

- `pipeline/prompts.py` — the prompt templates (primary target)
- `pipeline/rules_classifier.py` — if adding deterministic Uber/cab detection
- `pipeline/validator.py` — if improving counterparty matching logic
- `data/.llm_cache/classify_cache.json` — delete this to force fresh LLM calls after prompt changes
