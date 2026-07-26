"""Typing protocols for food and meal-item shaped inputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from app.db import QuantityUnit, ServingUnit


class SupportsFood(Protocol):
    serving_size: Decimal
    serving_unit: ServingUnit
    density_g_per_ml: Decimal | None
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


class SupportsMealItem(Protocol):
    food_id: int | None
    quantity: Decimal
    quantity_unit: QuantityUnit
    calories: Decimal | None
    protein_g: Decimal | None
    carbs_g: Decimal | None
    fat_g: Decimal | None
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None
