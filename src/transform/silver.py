"""Bronze → Silver: validate with Pydantic, dedupe, quarantine bad rows."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Type

ROW_COUNT_DROP_THRESHOLD  = 0.10  # warn if Silver has >10% fewer rows than Bronze
QUARANTINE_CRITICAL_THRESHOLD = 0.50  # critical if >50% of a batch is quarantined

import pandas as pd
from pydantic import BaseModel, ValidationError

from src.utils.logging_setup import log_event
from src.utils.schemas import OrderRow, CustomerRow, ProductRow


def _validate_df(
    df: pd.DataFrame,
    model: Type[BaseModel],
    primary_key: str,
    quarantine_path: Path,
    logger: logging.Logger,
    source_name: str,
) -> pd.DataFrame:
    """Validate each row with Pydantic. Good rows → Silver, bad rows → quarantine."""
    good, bad = [], []
    for _, row in df.iterrows():
        try:
            model(**row.to_dict())
            good.append(row)
        except (ValidationError, Exception) as exc:
            row_dict = row.to_dict()
            row_dict["_quarantine_reason"] = str(exc)
            row_dict["_quarantined_at"] = datetime.now(timezone.utc).isoformat()
            bad.append(row_dict)

    if bad:
        q_dir = quarantine_path / source_name
        q_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        pd.DataFrame(bad).to_parquet(q_dir / f"{ts}.parquet", index=False)
        log_event(logger, "WARNING", f"{source_name}_quarantined", count=len(bad))

        # Quarantine threshold alert — critical if majority of batch is rejected
        batch_size = len(df)
        quarantine_rate = len(bad) / batch_size if batch_size > 0 else 0
        if quarantine_rate > QUARANTINE_CRITICAL_THRESHOLD:
            log_event(logger, "CRITICAL", f"{source_name}_quarantine_critical",
                      quarantined=len(bad), batch_size=batch_size,
                      quarantine_pct=round(quarantine_rate * 100, 1),
                      message="Over half the batch was rejected — report will be near-empty")

    result = pd.DataFrame(good) if good else pd.DataFrame(columns=df.columns)

    # Deduplicate on primary key — keep last occurrence, log which IDs were duped
    if primary_key in result.columns and not result.empty:
        before = len(result)
        duped_ids = (
            result[result.duplicated(subset=[primary_key], keep="last")][primary_key]
            .tolist()
        )
        result = result.drop_duplicates(subset=[primary_key], keep="last")
        dupes = before - len(result)
        if dupes:
            log_event(logger, "INFO", f"{source_name}_deduped",
                      dropped=dupes, duplicate_ids=duped_ids)

    # Row-count threshold alert — warn if Silver retained <90% of Bronze rows
    bronze_count = len(df)
    silver_count = len(result)
    if bronze_count > 0:
        drop_rate = (bronze_count - silver_count) / bronze_count
        if drop_rate > ROW_COUNT_DROP_THRESHOLD:
            log_event(logger, "WARNING", f"{source_name}_high_drop_rate",
                      bronze_rows=bronze_count, silver_rows=silver_count,
                      drop_pct=round(drop_rate * 100, 1))

    return result.reset_index(drop=True)


def build_silver_orders(
    date_str: str,
    bronze_dir: Path,
    silver_dir: Path,
    quarantine_dir: Path,
    logger: logging.Logger,
) -> Path:
    src = bronze_dir / "orders" / f"date={date_str}" / "data.parquet"
    if not src.exists():
        log_event(logger, "WARNING", "silver_orders_no_bronze", date=date_str)
        return silver_dir / "orders" / f"date={date_str}" / "data.parquet"

    df = pd.read_parquet(src)
    df = _validate_df(df, OrderRow, "order_id", quarantine_dir, logger, "orders")

    out_dir = silver_dir / "orders" / f"date={date_str}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    df.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "silver_orders_written", rows=len(df), date=date_str)
    return out_path


def build_silver_customers(
    bronze_dir: Path,
    silver_dir: Path,
    quarantine_dir: Path,
    logger: logging.Logger,
) -> Path:
    src = bronze_dir / "customers" / "data.parquet"
    if not src.exists():
        log_event(logger, "WARNING", "silver_customers_no_bronze")
        return silver_dir / "customers" / "data.parquet"

    df = pd.read_parquet(src)
    df = _validate_df(df, CustomerRow, "customer_id", quarantine_dir, logger, "customers")

    out_dir = silver_dir / "customers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    df.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "silver_customers_written", rows=len(df))
    return out_path


def build_silver_products(
    bronze_dir: Path,
    silver_dir: Path,
    quarantine_dir: Path,
    logger: logging.Logger,
) -> Path:
    src = bronze_dir / "products" / "data.parquet"
    if not src.exists():
        log_event(logger, "WARNING", "silver_products_no_bronze")
        return silver_dir / "products" / "data.parquet"

    df = pd.read_parquet(src)
    if df.empty:
        return silver_dir / "products" / "data.parquet"

    df = _validate_df(df, ProductRow, "product_id", quarantine_dir, logger, "products")

    out_dir = silver_dir / "products"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    df.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "silver_products_written", rows=len(df))
    return out_path
