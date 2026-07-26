"""Domain helpers and business rules.

The HTTP and MCP adapters call functions in this package so product rules are
implemented in one place.
"""

from app.domain.constants import FOOD_NAME_SIMILARITY_THRESHOLD
from app.domain.dto import ItemMacros
from app.domain.errors import (
    DomainError,
    FoodAmbiguousError,
    FoodNotFoundError,
)
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
    "FoodNotFoundError",
    "ItemMacros",
    "UnitNormalizationError",
    "compute_item_macros",
    "normalize_to_grams",
    "resolve_food",
]
