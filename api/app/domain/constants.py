"""Shared domain constants for nutrition math and food resolution."""

from __future__ import annotations

from decimal import Decimal
from typing import Final

MASS_TO_G: Final[dict[str, Decimal]] = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),
    "lb": Decimal("453.59237"),
}

VOLUME_TO_ML: Final[dict[str, Decimal]] = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "fl_oz": Decimal("29.5735295625"),
    "tsp": Decimal("4.92892159375"),
    "tbsp": Decimal("14.78676478125"),
    "cup": Decimal("236.5882365"),
}

DEFAULT_DENSITY: Final[Decimal] = Decimal("1")
FOOD_NAME_SIMILARITY_THRESHOLD: Final[float] = 0.35
RECENT_LOOKBACK_DAYS: Final[int] = 30
