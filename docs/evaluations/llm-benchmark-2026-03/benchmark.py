"""
LLM Model Benchmark: Quality vs Cost

Tests all configured models across two prompt strategies against a curated
20-transaction fixture with known ground truth.  Measures per-field accuracy
and cost to find the best quality-to-cost ratio.

Usage:
    python3 -m pipeline.benchmark                          # all models, all strategies
    python3 -m pipeline.benchmark --model claude-haiku-4-5  # single model
    python3 -m pipeline.benchmark --strategy single         # single-pass only
    python3 -m pipeline.benchmark --strategy two-pass       # two-pass only
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

RUN_TIMEOUT_S = 120  # max seconds per model+strategy run

from pipeline.config import (
    LLM_MODEL_MAP,
    MODEL_PRICING,
    REPO_ROOT,
)
from pipeline.llm_classifier import (
    LLMResponse,
    _call_llm,
    _parse_response,
)
from pipeline.models import (
    CanonicalTransaction,
    Channel,
    CounterpartyCategory,
    Direction,
    TxnType,
    UPIType,
)
from pipeline.prompts import (
    batch_classify_prompt,
    two_pass_category_prompt,
    two_pass_fields_prompt,
)
from pipeline.rules_classifier import classify_rules

FIXTURE_PATH = REPO_ROOT / "data" / "test" / "benchmark_20.json"
RESULTS_PATH = REPO_ROOT / "data" / "test" / "benchmark_results.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    model: str
    strategy: str
    total_fields: int = 0
    correct_fields: int = 0
    field_scores: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    elapsed_s: float = 0.0
    per_txn: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading the fixture
# ---------------------------------------------------------------------------

def load_fixture() -> list[dict]:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def fixture_to_canonical(items: list[dict]) -> list[CanonicalTransaction]:
    """Turn fixture dicts into CanonicalTransaction objects, then apply rules."""
    txns = []
    for i, item in enumerate(items):
        txn = CanonicalTransaction(
            txn_id=f"T_99{i:06d}",
            txn_date=item["txn_date"],
            account_id=item.get("account_id", "HDFC_SAL_3703"),
            source_statement="benchmark",
            direction=Direction(item["direction"]),
            amount=Decimal(item["amount"]),
            raw_description=item["raw_description"],
            ref_number=item.get("ref_number"),
        )
        txns.append(txn)

    classify_rules(txns)
    return txns


# ---------------------------------------------------------------------------
# Build work items (matching llm_classifier's format)
# ---------------------------------------------------------------------------

def _needs_for_txn(txn: CanonicalTransaction, ground_truth: dict) -> list[str]:
    """Determine which fields the LLM needs to fill, based on what rules left empty."""
    needs = []
    if txn.txn_type is None and ground_truth.get("expected_txn_type"):
        needs.append("txn_type")
    if (txn.channel and txn.channel.value == "UPI"
            and txn.upi_type is None
            and ground_truth.get("expected_upi_type") not in ("", "NA")):
        needs.append("upi_type")
    if txn.counterparty is None:
        needs.append("counterparty")
    if txn.counterparty_category is None:
        needs.append("counterparty_category")
    return needs


def _build_items(
    txns: list[CanonicalTransaction],
    fixture: list[dict],
) -> list[dict]:
    """Build the context dicts the prompts expect."""
    items = []
    for txn, gt in zip(txns, fixture):
        needs = _needs_for_txn(txn, gt)
        if not needs:
            needs = ["counterparty", "counterparty_category"]
        items.append({
            "id": txn.txn_id,
            "txn_date": str(txn.txn_date),
            "desc": txn.raw_description,
            "direction": txn.direction.value,
            "amount": str(txn.amount),
            "channel": txn.channel.value if txn.channel else "",
            "txn_type": txn.txn_type.value if txn.txn_type else "",
            "upi_type": txn.upi_type.value if txn.upi_type else "",
            "ref_number": txn.ref_number or "",
            "needs": ", ".join(f'"{n}"' for n in needs),
        })
    return items


# ---------------------------------------------------------------------------
# Run strategies
# ---------------------------------------------------------------------------

def run_single_pass(
    model_key: str,
    provider: str,
    model_id: str,
    items: list[dict],
) -> tuple[list[dict], int, int]:
    """Single-pass strategy: one call gets all fields.

    Returns (results, total_input_tokens, total_output_tokens).
    """
    system, user = batch_classify_prompt(items)
    resp = _call_llm(provider, model_id, system, user)
    results = _parse_response(resp.text)
    return results, resp.input_tokens, resp.output_tokens


def run_two_pass(
    model_key: str,
    provider: str,
    model_id: str,
    items: list[dict],
) -> tuple[list[dict], int, int]:
    """Two-pass strategy: pass 1 gets txn_type/upi_type/counterparty,
    pass 2 uses "txn_type counterparty" to get counterparty_category.

    Returns (merged_results, total_input_tokens, total_output_tokens).
    """
    total_in, total_out = 0, 0

    # Pass 1: get txn_type, upi_type, counterparty
    sys1, usr1 = two_pass_fields_prompt(items)
    resp1 = _call_llm(provider, model_id, sys1, usr1)
    pass1_results = _parse_response(resp1.text)
    total_in += resp1.input_tokens
    total_out += resp1.output_tokens

    # Build pass-2 input: "txn_type counterparty" for each transaction
    pass1_map = {r["id"]: r for r in pass1_results if "id" in r}

    pass2_items = []
    for item in items:
        p1 = pass1_map.get(item["id"], {})
        txn_type = p1.get("txn_type", item.get("txn_type", ""))
        counterparty = p1.get("counterparty", "")
        combo = f"{txn_type} {counterparty}".strip()

        pass2_items.append({
            "id": item["id"],
            "txn_type_counterparty": combo,
            "direction": item["direction"],
            "amount": item["amount"],
            "channel": item.get("channel", ""),
        })

    # Pass 2: get counterparty_category
    sys2, usr2 = two_pass_category_prompt(pass2_items)
    resp2 = _call_llm(provider, model_id, sys2, usr2)
    pass2_results = _parse_response(resp2.text)
    total_in += resp2.input_tokens
    total_out += resp2.output_tokens

    # Merge results: pass1 fields + pass2 category
    pass2_map = {r["id"]: r for r in pass2_results if "id" in r}
    merged = []
    for item in items:
        combined = {"id": item["id"]}
        p1 = pass1_map.get(item["id"], {})
        p2 = pass2_map.get(item["id"], {})
        for k, v in p1.items():
            if k != "id":
                combined[k] = v
        for k, v in p2.items():
            if k != "id":
                combined[k] = v
        merged.append(combined)

    return merged, total_in, total_out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_results(
    results: list[dict],
    fixture: list[dict],
    txns: list[CanonicalTransaction],
) -> RunResult:
    """Compare LLM results against ground truth and compute accuracy."""
    result_map = {r["id"]: r for r in results if "id" in r}
    run = RunResult(model="", strategy="")

    # Per-field tracking
    fields = ["txn_type", "upi_type", "counterparty", "counterparty_category"]
    for f in fields:
        run.field_scores[f] = {"correct": 0, "total": 0}

    for txn, gt in zip(txns, fixture):
        r = result_map.get(txn.txn_id, {})
        txn_detail = {"id": txn.txn_id, "desc": txn.raw_description[:60]}

        for fld in fields:
            expected = gt.get(f"expected_{fld}", "")
            if not expected or expected == "NA":
                continue

            # Get the LLM's answer (may come from results or be pre-filled by rules)
            if fld == "txn_type":
                got = r.get("txn_type", txn.txn_type.value if txn.txn_type else "")
            elif fld == "upi_type":
                got = r.get("upi_type", txn.upi_type.value if txn.upi_type else "")
            elif fld == "counterparty":
                got = r.get("counterparty", txn.counterparty or "")
            elif fld == "counterparty_category":
                got = r.get("counterparty_category", "")
                if not got and txn.counterparty_category:
                    got = txn.counterparty_category.value
            else:
                got = ""

            run.field_scores[fld]["total"] += 1
            run.total_fields += 1

            match = _values_match(fld, str(got), expected)
            if match:
                run.field_scores[fld]["correct"] += 1
                run.correct_fields += 1
            else:
                txn_detail[f"{fld}_got"] = got
                txn_detail[f"{fld}_expected"] = expected

        run.per_txn.append(txn_detail)

    return run


def _values_match(field: str, got: str, expected: str) -> bool:
    """Flexible comparison depending on field type."""
    if not got or not expected:
        return False

    g = got.strip().lower()
    e = expected.strip().lower()

    if field == "counterparty":
        # Counterparty names can differ in casing and minor formatting.
        # Accept if one contains the other, or if they're equal ignoring case.
        return g == e or g in e or e in g

    if field == "counterparty_category":
        # Categories may have minor formatting diffs (commas, spacing).
        # Normalize by stripping commas and collapsing whitespace.
        g_norm = " ".join(g.replace(",", "").split())
        e_norm = " ".join(e.replace(",", "").split())
        return g_norm == e_norm

    # Enum fields: exact match (case-insensitive)
    return g == e


def compute_cost(run: RunResult, model_key: str) -> None:
    """Fill in cost_usd from token counts and pricing table."""
    pricing = MODEL_PRICING.get(model_key, {})
    if not pricing:
        return
    input_price = pricing["input"]
    output_price = pricing["output"]
    run.cost_usd = (
        run.input_tokens * input_price / 1_000_000
        + run.output_tokens * output_price / 1_000_000
    )


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(results: list[RunResult]) -> None:
    """Print a formatted comparison table to stdout."""
    print()
    print("=" * 95)
    print("LLM BENCHMARK RESULTS")
    print("=" * 95)

    # Separate successful runs from errors, sort successes by cost per correct field
    successful = [r for r in results if r.total_fields > 0]
    errored = [r for r in results if r.total_fields == 0]
    for r in successful:
        r._sort_key = r.cost_usd / max(r.correct_fields, 1)
    successful.sort(key=lambda r: r._sort_key)
    results = successful + errored

    header = (
        f"{'Model':<25s} {'Strategy':<10s} {'Accuracy':>8s} {'Cat.Acc':>8s} "
        f"{'Tokens':>10s} {'Cost($)':>10s} {'$/correct':>10s}"
    )
    print(header)
    print("-" * 95)

    for r in results:
        overall_acc = (
            f"{100 * r.correct_fields / r.total_fields:.1f}%"
            if r.total_fields else "N/A"
        )
        cat = r.field_scores.get("counterparty_category", {})
        cat_acc = (
            f"{100 * cat['correct'] / cat['total']:.1f}%"
            if cat.get("total") else "N/A"
        )
        tokens_str = f"{r.input_tokens + r.output_tokens:,}"
        cost_str = f"${r.cost_usd:.5f}"
        per_correct = (
            f"${r.cost_usd / max(r.correct_fields, 1):.6f}"
        )

        print(
            f"{r.model:<25s} {r.strategy:<10s} {overall_acc:>8s} {cat_acc:>8s} "
            f"{tokens_str:>10s} {cost_str:>10s} {per_correct:>10s}"
        )

    print("=" * 95)

    # Per-field breakdown for best model
    if results:
        best = results[0]
        print(f"\nBest value: {best.model} ({best.strategy})")
        print("Per-field accuracy:")
        for fld, scores in best.field_scores.items():
            t = scores["total"]
            c = scores["correct"]
            pct = f"{100 * c / t:.0f}%" if t else "N/A"
            print(f"  {fld:30s} {c}/{t} ({pct})")

        # Show mismatches for the best model
        mismatches = [
            t for t in best.per_txn
            if any(k.endswith("_got") for k in t)
        ]
        if mismatches:
            print(f"\nMismatches ({len(mismatches)} transactions):")
            for m in mismatches:
                print(f"  {m['id']}  {m['desc']}")
                for k, v in m.items():
                    if k.endswith("_got"):
                        fld = k.replace("_got", "")
                        print(f"    {fld}: got={v}  expected={m.get(fld + '_expected', '?')}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    fixture = load_fixture()
    print(f"Loaded {len(fixture)} transactions from {FIXTURE_PATH}")

    # Determine which models and strategies to run
    if args.model:
        if args.model not in LLM_MODEL_MAP:
            print(f"Unknown model: {args.model!r}")
            print(f"Available: {list(LLM_MODEL_MAP)}")
            sys.exit(1)
        model_keys = [args.model]
    else:
        model_keys = list(LLM_MODEL_MAP.keys())

    strategies = []
    if args.strategy in (None, "single"):
        strategies.append("single")
    if args.strategy in (None, "two-pass"):
        strategies.append("two-pass")

    total_runs = len(model_keys) * len(strategies)
    print(f"Running {total_runs} benchmark runs: {len(model_keys)} models x {len(strategies)} strategies\n")

    all_results: list[RunResult] = []
    run_num = 0

    for model_key in model_keys:
        provider, model_id = LLM_MODEL_MAP[model_key]

        for strategy in strategies:
            run_num += 1
            print(f"[{run_num}/{total_runs}] {model_key} / {strategy}...", end=" ", flush=True)

            # Fresh canonical objects for each run (rules are re-applied)
            txns = fixture_to_canonical(fixture)
            items = _build_items(txns, fixture)

            t0 = time.time()

            def _timeout_handler(signum, frame):
                raise TimeoutError(f"Run exceeded {RUN_TIMEOUT_S}s timeout")

            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(RUN_TIMEOUT_S)

            try:
                if strategy == "single":
                    results, tok_in, tok_out = run_single_pass(
                        model_key, provider, model_id, items
                    )
                else:
                    results, tok_in, tok_out = run_two_pass(
                        model_key, provider, model_id, items
                    )
            except Exception as e:
                elapsed = time.time() - t0
                print(f"ERROR ({elapsed:.1f}s): {e}")
                err_result = RunResult(
                    model=model_key, strategy=strategy, elapsed_s=elapsed
                )
                err_result.errors.append(str(e))
                all_results.append(err_result)
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
                continue
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

            elapsed = time.time() - t0

            run_result = score_results(results, fixture, txns)
            run_result.model = model_key
            run_result.strategy = strategy
            run_result.input_tokens = tok_in
            run_result.output_tokens = tok_out
            run_result.elapsed_s = elapsed
            compute_cost(run_result, model_key)

            acc = (
                f"{100 * run_result.correct_fields / run_result.total_fields:.0f}%"
                if run_result.total_fields else "N/A"
            )
            print(
                f"{acc} accuracy, "
                f"{tok_in + tok_out:,} tokens, "
                f"${run_result.cost_usd:.5f}, "
                f"{elapsed:.1f}s"
            )

            all_results.append(run_result)

    # Print the comparison table
    print_report(all_results)

    # Save raw results to JSON
    _save_results(all_results)


def _save_results(results: list[RunResult]) -> None:
    """Persist results to a JSON file for later analysis."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = []
    for r in results:
        data.append({
            "model": r.model,
            "strategy": r.strategy,
            "total_fields": r.total_fields,
            "correct_fields": r.correct_fields,
            "field_scores": r.field_scores,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd,
            "elapsed_s": r.elapsed_s,
            "per_txn": r.per_txn,
            "errors": r.errors,
        })
    with open(RESULTS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Results saved to {RESULTS_PATH}")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LLM Model Benchmark: Quality vs Cost")
    p.add_argument(
        "--model", type=str, default=None,
        help="Run only this model (e.g. claude-haiku-4-5)",
    )
    p.add_argument(
        "--strategy", type=str, default=None, choices=["single", "two-pass"],
        help="Run only this strategy",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    main()
