"""Ingest customers nested JSON → Bronze parquet."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.utils.exceptions import IngestionError
from src.utils.logging_setup import log_event
from src.transform.schema_check import check_schema

EXPECTED_COLUMNS = [
    "customer_id", "first_name", "last_name", "email",
    "city", "country", "signup_date", "tier",
]


def ingest_customers(
    landing_dir: Path,
    bronze_dir: Path,
    logger: logging.Logger,
    flatten: list[dict] | None = None,
) -> Path:
    """Flatten nested JSON export and write to Bronze. Returns output path.

    ``flatten`` is a list of ``{nested: 'parent.field', target: 'field'}``
    mappings read from pipeline.yaml.  Falls back to the legacy hardcoded
    address fields when not supplied so existing call-sites without config
    continue to work.
    """
    src = landing_dir / "customers.json"
    if not src.exists():
        raise IngestionError(f"customers file not found: {src}")

    raw = json.loads(src.read_text())

    # Build a lookup: parent_key -> [(dot_path, target_col), ...]
    # e.g. "address" -> [("address.city", "city"), ("address.country", "country")]
    if flatten is None:
        # Legacy fallback — keeps behaviour identical to the original hardcode
        flatten = [
            {"nested": "address.city",    "target": "city"},
            {"nested": "address.country", "target": "country"},
        ]

    from collections import defaultdict
    parent_map: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for entry in flatten:
        parts = entry["nested"].split(".", 1)
        parent_map[parts[0]].append((parts[1] if len(parts) > 1 else "", entry["target"]))

    rows = []
    for rec in raw:
        for parent, fields in parent_map.items():
            nested = rec.pop(parent, {})
            for field, target in fields:
                rec[target] = nested.get(field, "") if field else nested
        rows.append(rec)

    df = pd.DataFrame(rows)
    log_event(logger, "INFO", "customers_ingested", rows=len(df))

    check_schema(list(df.columns), EXPECTED_COLUMNS, "customers", logger)

    df["_source_file"] = src.name
    df["_ingested_at"] = datetime.now(timezone.utc).isoformat()

    out_dir = bronze_dir / "customers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    df.to_parquet(out_path, index=False)

    log_event(logger, "INFO", "customers_bronze_written", path=str(out_path), rows=len(df))
    return out_path
