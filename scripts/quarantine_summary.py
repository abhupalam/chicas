"""
Quarantine summary CLI.

Usage:
    python scripts/quarantine_summary.py
    python scripts/quarantine_summary.py --quarantine-dir data/quarantine
    python scripts/quarantine_summary.py --source orders

Reads all parquet files under the quarantine directory, groups rows by
failure reason, and prints a human-readable summary — no need to open
individual parquet files to investigate silent data loss.
"""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path

import pandas as pd


def summarise(quarantine_dir: Path, source_filter: str | None = None) -> None:
    pattern = "**/*.parquet"
    files = sorted(quarantine_dir.glob(pattern))

    if not files:
        print(f"No quarantine files found under {quarantine_dir}")
        return

    frames = []
    for f in files:
        source = f.parent.name          # e.g. "orders" or "customers"
        if source_filter and source != source_filter:
            continue
        df = pd.read_parquet(f)
        df["_source"] = source
        df["_quarantine_file"] = f.name
        frames.append(df)

    if not frames:
        print(f"No quarantine files found for source '{source_filter}'")
        return

    all_rows = pd.concat(frames, ignore_index=True)
    total = len(all_rows)

    print(f"\n{'='*60}")
    print(f"  QUARANTINE SUMMARY — {total} total rejected rows")
    print(f"{'='*60}\n")

    # ── Per-source breakdown ─────────────────────────────────────
    print("BY SOURCE:")
    for src, grp in all_rows.groupby("_source"):
        print(f"  {src:<20} {len(grp):>5} rows")

    # ── Failure reason breakdown ──────────────────────────────────
    print("\nBY FAILURE REASON (top 10):")
    if "_quarantine_reason" in all_rows.columns:
        # Trim Pydantic's verbose multi-line messages to first line only
        reasons = all_rows["_quarantine_reason"].str.split("\n").str[0]
        counts = Counter(reasons)
        for reason, count in counts.most_common(10):
            print(f"  [{count:>4}x]  {reason}")
    else:
        print("  (no _quarantine_reason column found)")

    # ── Date breakdown ────────────────────────────────────────────
    print("\nBY QUARANTINE DATE:")
    if "_quarantined_at" in all_rows.columns:
        dates = pd.to_datetime(all_rows["_quarantined_at"]).dt.date
        for d, count in sorted(Counter(dates).items(), reverse=True)[:7]:
            print(f"  {d}   {count} rows")

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quarantine summary report")
    parser.add_argument("--quarantine-dir", default="data/quarantine",
                        help="Path to quarantine root directory")
    parser.add_argument("--source", default=None,
                        help="Filter to a single source (e.g. orders, customers)")
    args = parser.parse_args()

    summarise(Path(args.quarantine_dir), args.source)


if __name__ == "__main__":
    main()
