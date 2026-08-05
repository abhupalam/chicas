"""
Tests for data integration improvements.
Run with: pytest -v tests/test_data_integration.py
"""
from __future__ import annotations

import json
import pytest
import pandas as pd
from src.pipeline import run_one_date
from src.ingest.customers import ingest_customers
from src.utils.config import Config
from tests.conftest import write_orders_csv, write_customers_json, make_products_db


DATE = "2025-11-07"

GOOD_CUSTOMER = {
    "customer_id": "CUST-001", "first_name": "Alice", "last_name": "Smith",
    "email": "alice@example.com", "address": {"city": "NYC", "country": "US"},
    "signup_date": "2024-01-01", "tier": "gold",
}
GOOD_PRODUCT = ("PROD-001", "Widget", "Electronics", 10.0, "SUP-A", "2025-01-01T00:00:00")


# ── Preflight checks ──────────────────────────────────────────────────────────

def test_preflight_fails_on_missing_products_db(config: Config):
    """Pipeline should fail before writing any Bronze when products DB is absent."""
    write_orders_csv(config.landing_orders, DATE, [
        ["ORD-001", "CUST-001", "PROD-001", DATE, "2", "49.99", "shipped"],
    ])
    write_customers_json(config.landing_customers, [GOOD_CUSTOMER])
    # products DB intentionally not created

    result = run_one_date(DATE, config)
    assert result["status"] == "FAIL"
    assert "preflight" in result["error"].lower()
    # No Bronze output should have been written
    assert not (config.bronze / "orders").exists()


def test_preflight_fails_on_missing_orders_csv(config: Config):
    """Pipeline should fail before writing any Bronze when orders CSV is absent."""
    write_customers_json(config.landing_customers, [GOOD_CUSTOMER])
    make_products_db(config.landing_products_db, [GOOD_PRODUCT])
    # orders CSV intentionally not created

    result = run_one_date(DATE, config)
    assert result["status"] == "FAIL"
    assert "preflight" in result["error"].lower()
    assert not (config.bronze / "orders").exists()


# ── Config-driven JSON flattening ─────────────────────────────────────────────

def test_flatten_from_config_produces_correct_columns(config: Config, tmp_path):
    """Fields declared in config flatten map appear as top-level columns in Bronze."""
    src = config.landing_customers / "customers.json"
    src.write_text(json.dumps([{
        "customer_id": "CUST-001", "first_name": "Alice", "last_name": "Smith",
        "email": "alice@example.com",
        "address": {"city": "NYC", "country": "US"},
        "signup_date": "2024-01-01", "tier": "gold",
    }]))
    import logging
    logger = logging.getLogger("test")
    flatten = [
        {"nested": "address.city",    "target": "city"},
        {"nested": "address.country", "target": "country"},
    ]
    ingest_customers(config.landing_customers, config.bronze, logger, flatten=flatten)
    df = pd.read_parquet(config.bronze / "customers" / "data.parquet")
    assert "city" in df.columns
    assert "country" in df.columns
    assert "address" not in df.columns
    assert df.iloc[0]["city"] == "NYC"
    assert df.iloc[0]["country"] == "US"


def test_flatten_extra_field_via_config(config: Config):
    """Adding a new nested field via config — no code change required."""
    src = config.landing_customers / "customers.json"
    src.write_text(json.dumps([{
        "customer_id": "CUST-001", "first_name": "Alice", "last_name": "Smith",
        "email": "alice@example.com",
        "address": {"city": "NYC", "country": "US", "zip_code": "10001"},
        "signup_date": "2024-01-01", "tier": "gold",
    }]))
    import logging
    logger = logging.getLogger("test")
    flatten = [
        {"nested": "address.city",     "target": "city"},
        {"nested": "address.country",  "target": "country"},
        {"nested": "address.zip_code", "target": "zip_code"},
    ]
    ingest_customers(config.landing_customers, config.bronze, logger, flatten=flatten)
    df = pd.read_parquet(config.bronze / "customers" / "data.parquet")
    assert "zip_code" in df.columns
    assert df.iloc[0]["zip_code"] == "10001"


def test_flatten_config_flows_through_pipeline(config: Config):
    """End-to-end: flatten map in config is used when pipeline runs."""
    write_orders_csv(config.landing_orders, DATE, [
        ["ORD-001", "CUST-001", "PROD-001", DATE, "2", "49.99", "shipped"],
    ])
    write_customers_json(config.landing_customers, [GOOD_CUSTOMER])
    make_products_db(config.landing_products_db, [GOOD_PRODUCT])

    result = run_one_date(DATE, config)
    assert result["status"] == "SUCCESS"
    df = pd.read_parquet(config.bronze / "customers" / "data.parquet")
    assert df.iloc[0]["city"] == "NYC"
    assert df.iloc[0]["country"] == "US"
