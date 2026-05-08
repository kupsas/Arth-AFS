#!/usr/bin/env python3
"""
One-shot bootstrap: scan ``data/.nse_cache`` bhav CSVs and write ``consolidated_isin_map.json``.

Run after backfilling bhav files (or in CI with a fixture cache). Daily updates happen
automatically from :func:`api.services.price_feed.refresh_all_prices` via
:func:`pipeline.isin_nse_resolver.update_consolidated_map_from_bhav`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pipeline.bhav_isin_map import (
    DEFAULT_DELISTED_CANDIDATES_PATH,
    DEFAULT_NSE_CACHE_DIR,
    consolidate_all_cached_bhavs,
    consolidated_isin_map_path,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build consolidated ISIN map from NSE bhav cache.")
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_NSE_CACHE_DIR,
        help="Directory containing cm*bhav.csv and BhavCopy_NSE_CM_*.csv (default: data/.nse_cache)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: consolidated path from ARTH_ISIN_MAP_PATH or data/.nse_cache/)",
    )
    p.add_argument(
        "--candidates-out",
        type=Path,
        default=DEFAULT_DELISTED_CANDIDATES_PATH,
        help="Where to write delisted ISIN candidate report",
    )
    p.add_argument(
        "--lookback-days",
        type=int,
        default=180,
        help="ISINs not seen in the last N calendar days (vs latest bhav file) go to candidates report",
    )
    args = p.parse_args(argv)
    out = args.out or consolidated_isin_map_path()
    m = consolidate_all_cached_bhavs(
        args.cache_dir,
        out_path=out,
        candidates_path=args.candidates_out,
        lookback_days=args.lookback_days,
    )
    logger.info("Done — %d ISIN rows in %s", len(m), out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
