"""Domain helpers and business rules.

The HTTP and MCP adapters call functions in this package so product rules are
implemented in one place.
"""

from app.domain.constants import FOOD_NAME_SIMILARITY_THRESHOLD
from app.domain.dto import (
    FoodCandidate,
    ItemMacros,
    MealItemResponse,
    MealItemSpec,
    MealResponse,
)
from app.domain.errors import (
    DomainError,
    FoodAmbiguousError,
    FoodDuplicateError,
    FoodNotFoundError,
    IntervalsUnavailableError,
    MealItemNotFoundError,
    MealNotFoundError,
    ServingUnitImmutableError,
    TemplateNotFoundError,
    UnauthorizedError,
)
from app.domain.food_resolution import resolve_food
from app.domain.meal_deletion import delete_meal, delete_meal_item
from app.domain.meal_logging import log_meal
from app.domain.meal_timing import infer_meal_type, parse_local_date, resolve_meal_type
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
    "FoodDuplicateError",
    "FoodNotFoundError",
    "IntervalsUnavailableError",
    "ItemMacros",
    "MealItemNotFoundError",
    "MealItemResponse",
    "MealItemSpec",
    "MealNotFoundError",
    "MealResponse",
    "ServingUnitImmutableError",
    "TemplateNotFoundError",
    "UnauthorizedError",
    "UnitNormalizationError",
    "compute_item_macros",
    "delete_meal",
    "delete_meal_item",
    "infer_meal_type",
    "log_meal",
    "normalize_to_grams",
    "parse_local_date",
    "resolve_food",
    "resolve_meal_type",
]
