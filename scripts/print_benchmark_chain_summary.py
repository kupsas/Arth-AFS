#!/usr/bin/env python3
"""
Print single-pass benchmark rows for models in pipeline.config.LLM_FALLBACK_CHAIN.

Run from repo root after regenerating data/test/benchmark_results.json. When the primary
model's `cost_usd` changes, refresh `ONBOARDING_PRIMARY_COST_USD_PER_100` in
`dashboard/src/data/classification-llm-education.ts` (or copy from this script's output).

  python3 scripts/print_benchmark_chain_summary.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline.config import LLM_FALLBACK_CHAIN, LLM_MODEL_MAP  # noqa: E402

RESULTS_PATH = REPO / "data" / "test" / "benchmark_results.json"


def main() -> None:
    data = json.loads(RESULTS_PATH.read_text())
    by_model: dict[str, dict] = {}
    for row in data:
        if row.get("strategy") != "single":
            continue
        if not row.get("total_fields"):
            continue
        by_model[row["model"]] = row

    print("LLM_FALLBACK_CHAIN benchmark (single-pass)\n")
    for i, key in enumerate(LLM_FALLBACK_CHAIN, start=1):
        prov, api_id = LLM_MODEL_MAP[key]
        r = by_model.get(key)
        if not r:
            print(f"{i}. {key} — NO single-pass row in results file")
            continue
        c, t = r["correct_fields"], r["total_fields"]
        pct = 100 * c / t if t else 0
        cost = r["cost_usd"]
        est100 = cost * (100 / 20)
        print(
            f"{i}. {key} ({prov}) {api_id}\n"
            f"   accuracy {c}/{t} ({pct:.1f}%)  cost_20usd ${cost:.6f}  est_100usd ${est100:.6f}\n"
        )


if __name__ == "__main__":
    main()
