"""
Tests for:
  - Historical Context: SCD Type 2 customer dimension preserves address history
  - Observability: stage failures produce structured logs with full tracebacks
"""
from __future__ import annotations
import json
import logging
from pathlib import Path

import pandas as pd
import pytest

from tests.conftest import write_orders_csv, write_customers_json, make_products_db
from src.pipeline import run_one_date
from src.utils.config import Config
from src.utils.logging_setup import log_event

DATE = "2025-11-07"

CUSTOMER_NYC = {
    "customer_id": "CUST-001", "first_name": "Alice", "last_name": "Smith",
    "email": "alice@example.com",
    "address": {"city": "NYC", "country": "US"},
    "signup_date": "2024-01-01", "tier": "gold",
}
CUSTOMER_LA = {
    "customer_id": "CUST-001", "first_name": "Alice", "last_name": "Smith",
    "email": "alice@example.com",
    "address": {"city": "LA", "country": "US"},   # ← moved city
    "signup_date": "2024-01-01", "tier": "gold",
}
GOOD_PRODUCT = ("PROD-001", "Widget", "Electronics", 10.0, "SUP-A", "2025-01-01T00:00:00")
GOOD_ORDER = ["ORD-001", "CUST-001", "PROD-001", DATE, "1", "9.99", "shipped"]


# ── SCD Type 2: Historical Context ───────────────────────────────────────────

class TestSCD2HistoricalContext:
    """Verify that address changes produce a new row and the old row is kept."""

    def _run(self, config: Config, customer: dict) -> pd.DataFrame:
        write_orders_csv(config.landing_orders, DATE, [GOOD_ORDER])
        write_customers_json(config.landing_customers, [customer])
        make_products_db(config.landing_products_db, [GOOD_PRODUCT])
        run_one_date(DATE, config)
        return pd.read_parquet(config.gold / "dim_customer.parquet")

    def test_initial_load_creates_open_row(self, config: Config):
        dim = self._run(config, CUSTOMER_NYC)
        assert len(dim) == 1
        row = dim.iloc[0]
        assert row["_current"] is True or row["_current"] == True
        assert row["_eff_end"] == "9999-12-31"
        assert row["city"] == "NYC"

    def test_address_change_adds_new_row(self, config: Config):
        """Second run with a different city → two rows in dim_customer."""
        # Run 1: NYC
        write_orders_csv(config.landing_orders, DATE, [GOOD_ORDER])
        write_customers_json(config.landing_customers, [CUSTOMER_NYC])
        make_products_db(config.landing_products_db, [GOOD_PRODUCT])
        run_one_date(DATE, config)

        # Run 2: moved to LA
        write_customers_json(config.landing_customers, [CUSTOMER_LA])
        run_one_date(DATE, config)

        dim = pd.read_parquet(config.gold / "dim_customer.parquet")
        assert len(dim) == 2, (
            f"Expected 2 history rows (old + new), got {len(dim)}:\n{dim}"
        )

    def test_old_row_is_expired_not_deleted(self, config: Config):
        """The NYC row must survive in dim_customer with _current=False."""
        write_orders_csv(config.landing_orders, DATE, [GOOD_ORDER])
        write_customers_json(config.landing_customers, [CUSTOMER_NYC])
        make_products_db(config.landing_products_db, [GOOD_PRODUCT])
        run_one_date(DATE, config)

        write_customers_json(config.landing_customers, [CUSTOMER_LA])
        run_one_date(DATE, config)

        dim = pd.read_parquet(config.gold / "dim_customer.parquet")
        old = dim[dim["city"] == "NYC"]
        assert len(old) == 1, "NYC row should still exist"
        assert old.iloc[0]["_current"] == False
        assert old.iloc[0]["_eff_end"] != "9999-12-31"

    def test_new_row_is_current(self, config: Config):
        """After a move, only the LA row should be marked _current."""
        write_orders_csv(config.landing_orders, DATE, [GOOD_ORDER])
        write_customers_json(config.landing_customers, [CUSTOMER_NYC])
        make_products_db(config.landing_products_db, [GOOD_PRODUCT])
        run_one_date(DATE, config)

        write_customers_json(config.landing_customers, [CUSTOMER_LA])
        run_one_date(DATE, config)

        dim = pd.read_parquet(config.gold / "dim_customer.parquet")
        current = dim[dim["_current"] == True]
        assert len(current) == 1
        assert current.iloc[0]["city"] == "LA"

    def test_unchanged_customer_stays_one_row(self, config: Config):
        """No change → second run must NOT add a duplicate row."""
        write_orders_csv(config.landing_orders, DATE, [GOOD_ORDER])
        write_customers_json(config.landing_customers, [CUSTOMER_NYC])
        make_products_db(config.landing_products_db, [GOOD_PRODUCT])
        run_one_date(DATE, config)
        run_one_date(DATE, config)  # identical second run

        dim = pd.read_parquet(config.gold / "dim_customer.parquet")
        assert len(dim) == 1, "Idempotent run must not duplicate unchanged rows"


# ── Observability: structured failure logs ────────────────────────────────────

class TestObservability:
    """Verify that pipeline failures emit structured logs with traceback."""

    def test_stage_failure_logs_traceback(self, config: Config, tmp_path: Path):
        """A failing stage must produce a log entry with a non-empty traceback."""
        # Deliberately omit the customers file so ingest_customers raises
        write_orders_csv(config.landing_orders, DATE, [GOOD_ORDER])
        make_products_db(config.landing_products_db, [GOOD_PRODUCT])
        # customers.json intentionally absent

        result = run_one_date(DATE, config)
        assert result["status"] == "FAIL"

        # The failing stage entry in the run metadata must have a traceback
        failed_stages = [s for s in result["stages"] if s["status"] == "FAIL"]
        assert failed_stages, "Expected at least one failed stage"
        assert "traceback" in failed_stages[0], "Stage entry must include 'traceback' key"
        assert len(failed_stages[0]["traceback"]) > 0, "Traceback must be non-empty"

    def test_stage_failure_logged_to_file(self, config: Config):
        """A stage failure must write a structured JSON ERROR line to pipeline.jsonl."""
        import logging as _logging
        # Clear any cached logger so a fresh FileHandler pointing at this
        # test's tmp logs directory is created by run_one_date.
        cached = _logging.getLogger("novacart")
        for h in list(cached.handlers):
            h.close()
            cached.removeHandler(h)

        write_orders_csv(config.landing_orders, DATE, [GOOD_ORDER])
        make_products_db(config.landing_products_db, [GOOD_PRODUCT])

        run_one_date(DATE, config)

        log_path = config.logs / "pipeline.jsonl"
        assert log_path.exists(), "Log file must be created"

        lines = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
        error_lines = [l for l in lines if l.get("level") == "ERROR"]
        assert error_lines, "At least one ERROR entry must be present in the log"
        first_error = error_lines[0]
        assert "traceback" in first_error, "ERROR log entry must contain 'traceback'"
        assert "stage" in first_error, "ERROR log entry must name the failed stage"

    def test_log_event_auto_captures_traceback(self, config: Config):
        """log_event at ERROR level inside an except block captures traceback."""
        import io
        logger = logging.getLogger("test_observability_auto_tb")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        buf = io.StringIO()
        sh = logging.StreamHandler(buf)
        sh.setLevel(logging.DEBUG)
        logger.addHandler(sh)

        try:
            raise ValueError("deliberate test error")
        except ValueError:
            log_event(logger, "ERROR", "test_failure", context="unit_test")

        logger.removeHandler(sh)
        output = buf.getvalue().strip()
        assert output, "Expected log output"
        entry = json.loads(output)
        assert entry["level"] == "ERROR"
        assert "traceback" in entry
        assert "deliberate test error" in entry["traceback"]
