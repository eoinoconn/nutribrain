"""Domain helpers and business rules.

The HTTP and MCP adapters call functions in this package so product rules are
implemented in one place.
"""

from app.domain.constants import FOOD_NAME_SIMILARITY_THRESHOLD
from app.domain.day_aggregation import get_day, get_range
from app.domain.dto import (
    DayMealGroup,
    DayResponse,
    EffectiveTarget,
    FoodCandidate,
    ItemMacros,
    MealItemResponse,
    MealItemSpec,
    MealResponse,
    PeriodTotals,
    RangeResponse,
    SetTargetResult,
    SyncIntervalsResult,
    TargetRow,
    TemplateItemResponse,
    TemplateItemSpec,
    TemplateResponse,
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
from app.domain.foods import (
    AddFoodResult,
    FoodSearchResult,
    UpdateFoodResult,
    add_food,
    delete_food,
    search_foods,
    set_favorite_food,
    update_food,
)
from app.domain.intervals_sync import sync_intervals
from app.domain.meal_deletion import delete_meal, delete_meal_item
from app.domain.meal_logging import log_meal
from app.domain.meal_timing import infer_meal_type, parse_local_date, resolve_meal_type
from app.domain.nutrition_math import (
    UnitNormalizationError,
    compute_item_macros,
    normalize_to_grams,
)
from app.domain.targets import get_effective_target, list_targets, set_target
from app.domain.templates import (
    create_template,
    delete_template,
    list_templates,
    log_template,
    update_template,
)

__all__ = [
    "FOOD_NAME_SIMILARITY_THRESHOLD",
    "AddFoodResult",
    "DayMealGroup",
    "DayResponse",
    "DomainError",
    "EffectiveTarget",
    "FoodAmbiguousError",
    "FoodCandidate",
    "FoodDuplicateError",
    "FoodNotFoundError",
    "FoodSearchResult",
    "IntervalsUnavailableError",
    "ItemMacros",
    "MealItemNotFoundError",
    "MealItemResponse",
    "MealItemSpec",
    "MealNotFoundError",
    "MealResponse",
    "PeriodTotals",
    "RangeResponse",
    "ServingUnitImmutableError",
    "SetTargetResult",
    "SyncIntervalsResult",
    "TargetRow",
    "TemplateItemResponse",
    "TemplateItemSpec",
    "TemplateNotFoundError",
    "TemplateResponse",
    "UnauthorizedError",
    "UnitNormalizationError",
    "UpdateFoodResult",
    "add_food",
    "compute_item_macros",
    "create_template",
    "delete_food",
    "delete_meal",
    "delete_meal_item",
    "delete_template",
    "get_day",
    "get_effective_target",
    "get_range",
    "infer_meal_type",
    "list_targets",
    "list_templates",
    "log_meal",
    "log_template",
    "normalize_to_grams",
    "parse_local_date",
    "resolve_food",
    "resolve_meal_type",
    "search_foods",
    "set_favorite_food",
    "set_target",
    "sync_intervals",
    "update_food",
    "update_template",
]
