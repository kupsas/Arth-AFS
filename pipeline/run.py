"""
CLI entry point for the raw-to-canonical pipeline.

Usage:
    python3 -m pipeline.run                                # default source, write to DB
    python3 -m pipeline.run --source hdfc_savings           # explicit source
    python3 -m pipeline.run --all-sources                   # run all 4 sources sequentially
    python3 -m pipeline.run --all-sources --llm none        # fast rules-only pass for all
    python3 -m pipeline.run --csv                           # legacy CSV output instead of DB
    python3 -m pipeline.run --validate                      # also run validator vs GSheet
    python3 -m pipeline.run --llm gemini-3.1-flash-lite     # force a specific model
    python3 -m pipeline.run --llm none                      # rules-only, no LLM

The pipeline stages run in order:
    1. Parse  →  2. Transform  →  3. Rules classify  →  4. LLM classify  →  5. Write (DB or CSV)
    (optional)  6. Validate against GSheet benchmark
"""

from __future__ import annotations

import argparse
import sys
import time

from pipeline import config
from pipeline.llm_classifier import classify_llm
from pipeline.models import CanonicalTransaction
from pipeline.parsers import PARSER_REGISTRY
from pipeline.rules_classifier import classify_rules
from pipeline.transformer import transform
from pipeline.writer import write_csv


def _run_single_source(
    source_key: str,
    *,
    input_file: str | None = None,
    write_to_csv: bool = False,
    output_file: str | None = None,
) -> list[CanonicalTransaction]:
    """Run the full pipeline for one source and persist results.

    Returns the list of enriched transactions (useful for validation).
    """
    if source_key not in PARSER_REGISTRY:
        print(f"Unknown source: {source_key!r}")
        print(f"Available: {list(PARSER_REGISTRY)}")
        sys.exit(1)

    source_cfg = config.SOURCE_CONFIGS[source_key]
    parser_cls = PARSER_REGISTRY[source_key]
    parser = parser_cls()

    resolved_input = input_file or config.DATA_DIR / source_cfg["source_statement"]
    print(f"Pipeline: source={source_key}  llm={config.LLM_MODEL}  file={resolved_input}")
    print()

    t0 = time.time()

    # ── Stage 1: Parse ──────────────────────────────────────────────
    print("[1/5] Parsing...")
    parsed = parser.parse(resolved_input)
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

    # ── Stage 5: Write ──────────────────────────────────────────────
    if write_to_csv:
        csv_path = output_file or config.OUTPUT_DIR / f"transactions_{source_key}.csv"
        print(f"[5/5] Writing CSV → {csv_path}")
        write_csv(canonical, csv_path)
    else:
        print("[5/5] Writing to SQLite DB...")
        from api.database import get_engine, init_db
        from pipeline.db_writer import write_to_db
        from sqlmodel import Session

        init_db()
        with Session(get_engine()) as session:
            run = write_to_db(
                canonical,
                source_key=source_key,
                llm_model=config.LLM_MODEL,
                session=session,
            )
        print(f"      → {run.new_count} new rows inserted, {run.updated_count} rows backfilled ({run.txn_count} total processed)")
        print(f"      → pipeline_run id={run.id}")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    return canonical


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.llm:
        config.LLM_MODEL = args.llm

    write_to_csv = args.csv

    if args.all_sources:
        # Run every source in SOURCE_CONFIGS sequentially
        print(f"Running all {len(config.SOURCE_CONFIGS)} sources...\n")
        for i, source_key in enumerate(config.SOURCE_CONFIGS, 1):
            print(f"{'=' * 60}")
            print(f"  Source {i}/{len(config.SOURCE_CONFIGS)}: {source_key}")
            print(f"{'=' * 60}")
            _run_single_source(source_key, write_to_csv=write_to_csv)
            print()
    else:
        canonical = _run_single_source(
            args.source,
            input_file=args.input,
            write_to_csv=write_to_csv,
            output_file=args.output,
        )

        # ── Optional: Validate ──────────────────────────────────────
        if args.validate:
            from pipeline.validator import print_report, validate
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
        "--all-sources", action="store_true",
        help="Run all sources in SOURCE_CONFIGS sequentially",
    )
    p.add_argument(
        "--input", type=str, default=None,
        help="Override input file path (single-source mode only)",
    )
    p.add_argument(
        "--output", type=str, default=None,
        help="Override output CSV path (requires --csv)",
    )
    p.add_argument(
        "--csv", action="store_true",
        help="Write to CSV instead of SQLite (legacy mode)",
    )
    p.add_argument(
        "--llm", type=str, default=None,
        help="Override LLM model (auto, none, or a specific model key)",
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
