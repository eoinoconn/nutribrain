"""Compatibility facade for legacy imports.

Prefer importing from app.domain package-level exports or focused modules:
- app.domain.nutrition_math
- app.domain.food_resolution
- app.domain.errors
- app.domain.dto
- app.domain.constants
"""

from app.domain.constants import FOOD_NAME_SIMILARITY_THRESHOLD
from app.domain.dto import FoodCandidate, ItemMacros
from app.domain.errors import DomainError, FoodAmbiguousError, FoodNotFoundError
from app.domain.food_resolution import resolve_food
from app.domain.nutrition_math import (
    UnitNormalizationError,
    compute_item_macros,
    normalize_to_grams,
)

__all__ = [
    "FOOD_NAME_SIMILARITY_THRESHOLD",
    "DomainError",
    "FoodAmbiguousError",
    "FoodCandidate",
    "FoodNotFoundError",
    "ItemMacros",
    "UnitNormalizationError",
    "compute_item_macros",
    "normalize_to_grams",
    "resolve_food",
]
