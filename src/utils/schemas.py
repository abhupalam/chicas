"""Pydantic schema contracts for Bronze → Silver validation."""
from __future__ import annotations
import re
from datetime import date
from typing import Optional
from pydantic import BaseModel, field_validator, ConfigDict

_EMAIL_RE = re.compile(
    r"""
    ^
    [a-zA-Z0-9._%+\-]+   # ── local part
    @                     # ── exactly one @
    [a-zA-Z0-9.\-]+       # ── domain (may include sub-domains)
    \.                    # ── dot before TLD 
    [a-zA-Z]{2,}          # ── TLD (2+ alpha chars)
    $
    """,
    re.VERBOSE,
)

def _validate_email_format(value: str) -> str:
    """
    Validate *value* as an e-mail address.

    Raises ValueError with a message that names specific structural 
    problem so  error logs are actionable.
    """
    # ── Guard 1: multiple "@" symbols
    at_count = value.count("@")
    if at_count == 0:
        raise ValueError(f"invalid email – missing '@': {value!r}")
    if at_count > 1:
        raise ValueError(
            f"invalid email – {at_count} '@' symbols found (expected 1): {value!r}"
        )

    local, domain = value.split("@")

    # ── Guard 2: empty local part
    if not local:
        raise ValueError(
            f"invalid email – local part (before '@') is empty: {value!r}"
        )
    
    # ── Guard 3: empty or TLD-less domain (e.g. user@ or user@domain)
    if not domain:
        raise ValueError(
            f"invalid email – domain (after '@') is empty: {value!r}"
        )
    if "." not in domain:
        raise ValueError(
            f"invalid email – domain has no TLD (expected 'domain.tld'): {value!r}"
        )

    # ── Guard 4: full structural check via compiled regex
    if not _EMAIL_RE.match(value):
        raise ValueError(
            f"invalid email – failed structural format check: {value!r}"
        )

    return value.lower()


class OrderRow(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=False)

    order_id: str
    customer_id: str
    product_id: str
    order_date: date
    quantity: int
    unit_price: float
    status: str

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"quantity must be > 0, got {v}")
        return v

    @field_validator("unit_price")
    @classmethod
    def price_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"unit_price must be >= 0, got {v}")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        allowed = {"pending", "shipped", "delivered", "cancelled", "returned"}
        if v.lower() not in allowed:
            raise ValueError(f"status '{v}' not in {allowed}")
        return v.lower()


class CustomerRow(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    email: str
    city: str
    country: str
    signup_date: date
    tier: Optional[str] = "standard"

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        return _validate_email_format(v)


class ProductRow(BaseModel):
    product_id: str
    name: str
    category: str
    unit_cost: float
    supplier_id: str
    updated_at: str  # ISO string from SQLite

    @field_validator("unit_cost")
    @classmethod
    def cost_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"unit_cost must be >= 0, got {v}")
        return v
