"""Small data objects shared across domain operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ItemMacros:
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


@dataclass(frozen=True, slots=True)
class FoodCandidate:
    id: int
    name: str
    calories: Decimal
    is_favorite: bool
    last_logged_at: datetime | None
