"""Tests for the enhanced _validate_email_format guards in CustomerRow."""
from __future__ import annotations
import pytest
from pydantic import ValidationError
from src.utils.schemas import CustomerRow


def _make(email: str) -> dict:
    return dict(
        customer_id="C1", first_name="Alice", last_name="Smith",
        email=email, city="NYC", country="US",
        signup_date="2024-01-01", tier="gold",
    )


# ── Valid addresses ────────────────────────────────────────────────────────────

class TestValidEmails:
    @pytest.mark.parametrize("email", [
        "user@example.com",
        "user.name+tag@sub.domain.org",
        "Alice@Example.COM",          # mixed case – normalised to lowercase
        "x@y.io",                     # minimal valid address
        "first.last@company.co.uk",   # multi-part TLD
    ])
    def test_accepted(self, email):
        row = CustomerRow(**_make(email))
        assert row.email == email.lower()


# ── Guard 1: missing or multiple "@" ──────────────────────────────────────────

class TestAtSymbolGuard:
    def test_missing_at_rejected(self):
        with pytest.raises(ValidationError, match="missing '@'"):
            CustomerRow(**_make("userexample.com"))

    def test_multiple_at_rejected(self):
        with pytest.raises(ValidationError, match="2 '@' symbols"):
            CustomerRow(**_make("a@b@c.com"))

    def test_three_at_symbols_rejected(self):
        with pytest.raises(ValidationError, match="3 '@' symbols"):
            CustomerRow(**_make("a@b@c@d.com"))


# ── Guard 2: empty local part ─────────────────────────────────────────────────

class TestEmptyLocalPart:
    def test_empty_local_rejected(self):
        with pytest.raises(ValidationError, match="local part.*empty"):
            CustomerRow(**_make("@example.com"))


# ── Guard 3: empty or TLD-less domain ─────────────────────────────────────────

class TestDomainGuard:
    def test_empty_domain_rejected(self):
        with pytest.raises(ValidationError, match="domain.*empty"):
            CustomerRow(**_make("user@"))

    def test_domain_without_tld_rejected(self):
        with pytest.raises(ValidationError, match="no TLD"):
            CustomerRow(**_make("user@domain"))


# ── Guard 4: regex structural check ───────────────────────────────────────────

class TestRegexGuard:
    @pytest.mark.parametrize("email", [
        "user @example.com",    # space in local part
        "user@exam ple.com",    # space in domain
        "user@.com",            # domain starts with dot
        "user@example.",        # TLD is empty after dot
        "@.com",                # empty local and bad domain
    ])
    def test_structurally_invalid_rejected(self, email):
        with pytest.raises(ValidationError):
            CustomerRow(**_make(email))
