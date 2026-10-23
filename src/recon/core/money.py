"""Money value object.

Amounts are `Decimal`, never `float`, and are always held at the currency's exact
precision. Construction is strict: an amount with more decimal places than the currency
allows is an error, not something silently rounded. Use `Money.rounded()` when you
genuinely want rounding (fees, FX, tax).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from functools import total_ordering

from recon.schemas.common import Currency

# ISO 4217 minor-unit exponent per supported currency (all four use 2 decimals).
CURRENCY_EXPONENTS: dict[Currency, int] = {
    Currency.AUD: 2,
    Currency.EUR: 2,
    Currency.USD: 2,
    Currency.GBP: 2,
}


class CurrencyMismatchError(ValueError):
    """Raised when arithmetic or ordering mixes two different currencies."""


def _coerce_decimal(value: object) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Money amounts must be Decimal, int or str, never float or bool")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid money amount: {value!r}") from exc
    else:
        raise TypeError(f"Unsupported money amount type: {type(value).__name__}")
    if not result.is_finite():
        raise ValueError("Money amounts must be finite")
    return result


def _quantum(currency: Currency) -> Decimal:
    """The smallest unit for a currency as a Decimal, e.g. Decimal('0.01') for AUD."""
    return Decimal(1).scaleb(-CURRENCY_EXPONENTS[currency])


@total_ordering
@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        currency = Currency(self.currency)
        raw = _coerce_decimal(self.amount)
        exact = raw.quantize(_quantum(currency), rounding=ROUND_HALF_EVEN)
        if exact != raw:
            raise ValueError(
                f"{raw} has more decimal places than {currency.value} allows; "
                "use Money.rounded() to round explicitly"
            )
        # Frozen dataclass: normalise the stored values via object.__setattr__.
        object.__setattr__(self, "amount", exact)
        object.__setattr__(self, "currency", currency)

    # ---- constructors ----
    @classmethod
    def of(cls, amount: Decimal | int | str, currency: Currency | str) -> Money:
        return cls(_coerce_decimal(amount), Currency(currency))

    @classmethod
    def zero(cls, currency: Currency | str) -> Money:
        return cls(Decimal(0), Currency(currency))

    @classmethod
    def from_minor_units(cls, minor: int, currency: Currency | str) -> Money:
        """Build from integer minor units, e.g. 1999 cents -> 19.99."""
        if isinstance(minor, bool) or not isinstance(minor, int):
            raise TypeError("minor units must be an int")
        cur = Currency(currency)
        return cls(Decimal(minor).scaleb(-CURRENCY_EXPONENTS[cur]), cur)

    @classmethod
    def rounded(
        cls,
        amount: Decimal | int | str,
        currency: Currency | str,
        rounding: str = ROUND_HALF_EVEN,
    ) -> Money:
        """Explicitly round to the currency's precision (banker's rounding by default)."""
        cur = Currency(currency)
        return cls(_coerce_decimal(amount).quantize(_quantum(cur), rounding=rounding), cur)

    # ---- conversion ----
    def to_minor_units(self) -> int:
        """Exact integer minor units, e.g. 19.99 -> 1999. This is what we store in the DB."""
        return int(self.amount.scaleb(CURRENCY_EXPONENTS[self.currency]))

    # ---- predicates ----
    def is_zero(self) -> bool:
        return self.amount == 0

    def is_positive(self) -> bool:
        return self.amount > 0

    def is_negative(self) -> bool:
        return self.amount < 0

    # ---- arithmetic (same currency only) ----
    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot combine {self.currency.value} with {other.currency.value}"
            )

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.amount), self.currency)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount < other.amount

    def __str__(self) -> str:
        return f"{self.amount} {self.currency.value}"