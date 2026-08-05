"""Referential integrity tests for OrderRow.with_refs()."""
from __future__ import annotations
from datetime import date
import pytest
from pydantic import ValidationError
from src.utils.schemas import OrderRow


def _base(**overrides) -> dict:
    row = dict(
        order_id="ORD-1",
        customer_id="C1",
        product_id="P1",
        order_date=date(2025, 1, 1),
        quantity=2,
        unit_price=9.99,
        status="shipped",
    )
    row.update(overrides)
    return row


class TestWithRefs:
    def test_valid_refs_accepted(self):
        BoundRow = OrderRow.with_refs({"C1"}, {"P1"})
        row = BoundRow(**_base())
        assert row.order_id == "ORD-1"

    def test_unknown_customer_rejected(self):
        BoundRow = OrderRow.with_refs({"C2"}, {"P1"})
        with pytest.raises(ValidationError, match="customer_id 'C1' not found"):
            BoundRow(**_base())

    def test_unknown_product_rejected(self):
        BoundRow = OrderRow.with_refs({"C1"}, {"P2"})
        with pytest.raises(ValidationError, match="product_id 'P1' not found"):
            BoundRow(**_base())

    def test_both_unknown_rejected(self):
        BoundRow = OrderRow.with_refs({"C2"}, {"P2"})
        with pytest.raises(ValidationError):
            BoundRow(**_base())

    def test_empty_customer_set_skips_check(self):
        """Empty set → no Silver data yet; check is skipped gracefully."""
        BoundRow = OrderRow.with_refs(set(), {"P1"})
        row = BoundRow(**_base())
        assert row.customer_id == "C1"

    def test_empty_product_set_skips_check(self):
        BoundRow = OrderRow.with_refs({"C1"}, set())
        row = BoundRow(**_base())
        assert row.product_id == "P1"

    def test_unbound_order_row_still_accepts_any_id(self):
        """Plain OrderRow has no ref check — existing behaviour is unchanged."""
        row = OrderRow(**_base(customer_id="GHOST-9999", product_id="GHOST-8888"))
        assert row.customer_id == "GHOST-9999"

    def test_with_refs_inherits_field_validators(self):
        """BoundOrderRow still enforces field-level rules (e.g. quantity > 0)."""
        BoundRow = OrderRow.with_refs({"C1"}, {"P1"})
        with pytest.raises(ValidationError, match="quantity must be > 0"):
            BoundRow(**_base(quantity=0))
