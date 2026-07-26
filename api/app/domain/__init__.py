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
    TemplateItemResponse,
    TemplateItemSpec,
    TemplateResponse,
)
from app.domain.errors import (
    DomainError,
    FoodAmbiguousError,
    FoodDuplicateError,
    FoodNotFoundError,
    ServingUnitImmutableError,
    TemplateNotFoundError,
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
    "ItemMacros",
    "MealItemResponse",
    "MealItemSpec",
    "MealResponse",
    "PeriodTotals",
    "RangeResponse",
    "ServingUnitImmutableError",
    "SetTargetResult",
    "TemplateItemResponse",
    "TemplateItemSpec",
    "TemplateNotFoundError",
    "TemplateResponse",
    "UnitNormalizationError",
    "UpdateFoodResult",
    "add_food",
    "compute_item_macros",
    "create_template",
    "delete_food",
    "delete_template",
    "get_day",
    "get_effective_target",
    "get_range",
    "infer_meal_type",
    "list_templates",
    "log_meal",
    "log_template",
    "normalize_to_grams",
    "parse_local_date",
    "resolve_food",
    "resolve_meal_type",
    "set_favorite_food",
    "set_target",
    "update_food",
    "update_template",
]
