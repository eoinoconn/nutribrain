"""Domain helpers and business rules.

The HTTP and MCP adapters call functions in this package so product rules are
implemented in one place.
"""

from app.domain.constants import FOOD_NAME_SIMILARITY_THRESHOLD
from app.domain.dto import (
    EffectiveTarget,
    FoodCandidate,
    ItemMacros,
    MealItemResponse,
    MealItemSpec,
    MealResponse,
    SetTargetResult,
)
from app.domain.errors import (
    DomainError,
    FoodAmbiguousError,
    FoodDuplicateError,
    FoodNotFoundError,
    ServingUnitImmutableError,
)
from app.domain.food_resolution import resolve_food
from app.domain.foods import (
    AddFoodResult,
    UpdateFoodResult,
    add_food,
    delete_food,
    set_favorite_food,
    update_food,
)
from app.domain.meal_logging import log_meal
from app.domain.meal_timing import infer_meal_type, parse_local_date, resolve_meal_type
from app.domain.nutrition_math import (
    UnitNormalizationError,
    compute_item_macros,
    normalize_to_grams,
)
from app.domain.targets import get_effective_target, set_target

__all__ = [
    "FOOD_NAME_SIMILARITY_THRESHOLD",
    "AddFoodResult",
    "DomainError",
    "EffectiveTarget",
    "FoodAmbiguousError",
    "FoodCandidate",
    "FoodDuplicateError",
    "FoodNotFoundError",
    "ItemMacros",
    "MealItemResponse",
    "MealItemSpec",
    "MealResponse",
    "SetTargetResult",
    "ServingUnitImmutableError",
    "UnitNormalizationError",
    "UpdateFoodResult",
    "add_food",
    "compute_item_macros",
    "get_effective_target",
    "delete_food",
    "infer_meal_type",
    "log_meal",
    "normalize_to_grams",
    "parse_local_date",
    "resolve_food",
    "resolve_meal_type",
    "set_target",
    "set_favorite_food",
    "update_food",
]
