"""
CLI entry point for the raw-to-canonical pipeline.

Usage:
    python3 -m pipeline.run                          # default: auto fallback chain
    python3 -m pipeline.run --source hdfc_savings     # explicit source
    python3 -m pipeline.run --validate                # also run validator vs GSheet
    python3 -m pipeline.run --llm gemini-3.1-flash-lite  # force a specific model
    python3 -m pipeline.run --llm none                # rules-only, no LLM

The pipeline stages run in order:
    1. Parse  →  2. Transform  →  3. Rules classify  →  4. LLM classify  →  5. Write CSV
    (optional)  6. Validate against GSheet benchmark
"""

from __future__ import annotations

import argparse
import sys
import time

from pipeline import config
from pipeline.llm_classifier import classify_llm
from pipeline.parsers import PARSER_REGISTRY
from pipeline.rules_classifier import classify_rules
from pipeline.transformer import transform
from pipeline.validator import print_report, validate
from pipeline.writer import write_csv


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    # Allow CLI to override the LLM model
    if args.llm:
        config.LLM_MODEL = args.llm

    source_key = args.source
    if source_key not in PARSER_REGISTRY:
        print(f"Unknown source: {source_key!r}")
        print(f"Available: {list(PARSER_REGISTRY)}")
        sys.exit(1)

    source_cfg = config.SOURCE_CONFIGS[source_key]
    parser_cls = PARSER_REGISTRY[source_key]
    parser = parser_cls()

    # Resolve input file
    input_file = args.input or config.DATA_DIR / source_cfg["source_statement"]

    print(f"Pipeline: source={source_key}  llm={config.LLM_MODEL}  file={input_file}")
    print()

    t0 = time.time()

    # ── Stage 1: Parse ──────────────────────────────────────────────
    print("[1/5] Parsing...")
    parsed = parser.parse(input_file)
    print(f"      → {len(parsed)} rows parsed")

    # ── Stage 2: Transform ──────────────────────────────────────────
    print("[2/5] Transforming...")
    canonical = transform(
        parsed,
        account_id=source_cfg["account_id"],
        currency=source_cfg.get("currency", "INR"),
        source_statement=source_cfg["source_statement"],
    )
    print(f"      → {len(canonical)} canonical rows")

    # ── Stage 3: Rules classify ─────────────────────────────────────
    print("[3/5] Rules classifier...")
    classify_rules(canonical)
    filled_type = sum(1 for t in canonical if t.txn_type)
    filled_ch = sum(1 for t in canonical if t.channel)
    print(f"      → txn_type filled: {filled_type}/{len(canonical)}")
    print(f"      → channel filled:  {filled_ch}/{len(canonical)}")

    # ── Stage 4: LLM classify ──────────────────────────────────────
    print(f"[4/5] LLM classifier (model={config.LLM_MODEL})...")
    classify_llm(canonical)
    filled_type = sum(1 for t in canonical if t.txn_type)
    filled_cp = sum(1 for t in canonical if t.counterparty)
    filled_cat = sum(1 for t in canonical if t.counterparty_category)
    print(f"      → txn_type filled: {filled_type}/{len(canonical)}")
    print(f"      → counterparty filled: {filled_cp}/{len(canonical)}")
    print(f"      → category filled: {filled_cat}/{len(canonical)}")

    # ── Stage 5: Write CSV ──────────────────────────────────────────
    output_file = args.output or config.OUTPUT_DIR / f"transactions_{source_key}.csv"
    print(f"[5/5] Writing CSV → {output_file}")
    write_csv(canonical, output_file)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")

    # ── Optional: Validate ──────────────────────────────────────────
    if args.validate:
        benchmark = args.benchmark or config.GSHEET_BENCHMARK_FILE
        print(f"\nValidating against {benchmark}...")
        result = validate(canonical, benchmark)
        print_report(result)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Raw-to-canonical transaction pipeline",
    )
    p.add_argument(
        "--source", default="hdfc_savings",
        help="Source key (default: hdfc_savings)",
    )
    p.add_argument(
        "--input", type=str, default=None,
        help="Override input file path",
    )
    p.add_argument(
        "--output", type=str, default=None,
        help="Override output CSV path",
    )
    p.add_argument(
        "--llm", type=str, default=None,
        help="Override LLM model (auto, none, or a specific model key like gemini-3.1-flash-lite)",
    )
    p.add_argument(
        "--validate", action="store_true",
        help="Run validator against GSheet benchmark after pipeline",
    )
    p.add_argument(
        "--benchmark", type=str, default=None,
        help="Override benchmark CSV for validation",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    main()
