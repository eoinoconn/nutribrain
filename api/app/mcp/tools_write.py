"""MCP write tools.

Descriptions intentionally encode product mutation rules so model callers avoid
history rewrites and other irreversible mistakes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from app.api.foods import FoodResponse
from app.db import MealType, QuantityUnit, ServingUnit
from app.domain import (
    MealItemSpec,
    TemplateItemSpec,
    add_food,
    create_template,
    delete_meal,
    delete_meal_item,
    delete_template,
    log_meal,
    log_template,
    set_favorite_food,
    set_target,
    update_food,
    update_meal,
    update_meal_item,
    update_template,
)
from app.domain.dto import MealItemResponse, MealResponse, TemplateResponse
from app.domain.dto import SetTargetResult as SetTargetDto
from app.domain.errors import DomainError
from app.domain.foods import AddFoodResult as AddFoodDomainResult
from app.domain.foods import UpdateFoodResult as UpdateFoodDomainResult
from app.mcp._tool_common import capture_domain_error, run_with_session
from app.mcp.date_args import resolve_date_arg
from app.mcp.serializers import (
    DeleteResultModel,
    MealItemModel,
    MealModel,
    SetTargetResultModel,
    TemplateModel,
    ToolErrorResponse,
    serialize_meal,
    serialize_meal_item,
    serialize_set_target_result,
    serialize_template,
)


class MealItemInput(BaseModel):
    name: str = Field(min_length=1)
    quantity: Decimal
    quantity_unit: QuantityUnit
    food_id: int | None = None
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None


class TemplateItemInput(BaseModel):
    name: str = Field(min_length=1)
    quantity: Decimal
    quantity_unit: QuantityUnit
    food_id: int | None = None
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None


type LogMealResult = MealModel | ToolErrorResponse
type LogTemplateResult = MealModel | ToolErrorResponse
type AddFoodResult = FoodResponse | ToolErrorResponse
type UpdateFoodResult = dict[str, object] | ToolErrorResponse
type TemplateResult = TemplateModel | ToolErrorResponse
type SetTargetResult = SetTargetResultModel | ToolErrorResponse
type DeleteResult = DeleteResultModel | ToolErrorResponse
type UpdateMealResult = MealModel | ToolErrorResponse
type UpdateMealItemResult = MealItemModel | ToolErrorResponse

# Sentinel default for update_meal_item_tool's food_id: unlike a plain `= None`
# default, this survives being unset by the MCP call (pydantic's argument
# validation only substitutes the Python default for a truly omitted key, and
# does not run that default value through validation, so this sentinel object
# passes straight through when the caller doesn't mention food_id at all).
# That distinction matters here specifically because None is a meaningful,
# consequential value for food_id (it converts the item to ad-hoc) — losing
# "omitted" vs "explicitly null" would make quantity-only edits on food-linked
# items spuriously demand macros. Plain `= None` (as used for the other
# optional fields below, mirroring update_food) is fine where the field is
# just cosmetic/optional and "leave alone" vs "clear" is low-stakes.
_FOOD_ID_UNSET: object = object()

# Same rationale as _FOOD_ID_UNSET, applied to update_meal_tool's notes: the
# domain function's notes parameter uses the "explicit clear" sentinel
# pattern (omit -> unchanged, pass None -> clear), so a plain `= None`
# default here would forward notes=None on every call that simply omits
# notes, silently wiping existing notes on unrelated single-field edits
# (e.g. a meal_type-only correction).
_NOTES_UNSET: object = object()


def register_write_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="log_meal",
        description=(
            "Log one meal with one or more items. Use this for normal meal logging; "
            "do not use update_food to fix a single meal because update_food rewrites "
            "historical totals for every meal using that food."
        ),
    )
    def log_meal_tool(
        items: list[MealItemInput],
        local_tz: str,
        logged_at: datetime | None = None,
        meal_type: str | None = None,
        notes: str | None = None,
    ) -> LogMealResult:
        when = logged_at or datetime.now(UTC)
        specs = [MealItemSpec(**item.model_dump()) for item in items]
        try:
            meal = cast(
                MealResponse,
                run_with_session(
                    log_meal,
                    items=specs,
                    logged_at=when,
                    local_tz=local_tz,
                    meal_type=meal_type,
                    notes=notes,
                ),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_meal(meal)

    @mcp.tool(
        name="log_template",
        description=(
            "Log a previously created template into a meal. Templates are user-initiated "
            "shortcuts and should only be used when the user explicitly wants a repeatable "
            "meal pattern."
        ),
    )
    def log_template_tool(
        template_id: int,
        local_tz: str,
        logged_at: datetime | None = None,
        meal_type: str | None = None,
        quantity_scale: Decimal = Decimal("1"),
        notes: str | None = None,
    ) -> LogTemplateResult:
        when = logged_at or datetime.now(UTC)
        try:
            meal = cast(
                MealResponse,
                run_with_session(
                    log_template,
                    template_id=template_id,
                    logged_at=when,
                    local_tz=local_tz,
                    meal_type=meal_type,
                    quantity_scale=quantity_scale,
                    notes=notes,
                ),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_meal(meal)

    @mcp.tool(
        name="add_food",
        description=(
            "Create a reusable food. Prefer serving_unit g or ml with serving_size equal "
            "to one natural unit's weight/volume. Use serving_unit piece only when the "
            "food cannot be represented by mass or volume."
        ),
    )
    def add_food_tool(
        name: str,
        serving_size: Decimal,
        serving_unit: ServingUnit,
        calories: Decimal,
        protein_g: Decimal,
        carbs_g: Decimal,
        fat_g: Decimal,
        fiber_g: Decimal | None = None,
        sat_fat_g: Decimal | None = None,
        sodium_mg: Decimal | None = None,
        density_g_per_ml: Decimal | None = None,
        force: bool = False,
    ) -> AddFoodResult:
        try:
            result = cast(
                AddFoodDomainResult,
                run_with_session(
                    add_food,
                    name=name,
                    serving_size=serving_size,
                    serving_unit=serving_unit,
                    calories=calories,
                    protein_g=protein_g,
                    carbs_g=carbs_g,
                    fat_g=fat_g,
                    fiber_g=fiber_g,
                    sat_fat_g=sat_fat_g,
                    sodium_mg=sodium_mg,
                    density_g_per_ml=density_g_per_ml,
                    force=force,
                ),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return FoodResponse.model_validate(result.food)

    @mcp.tool(
        name="update_food",
        description=(
            "Update a reusable food and recompute all historical meals that reference it. "
            "Never use this to fix one meal entry; edit that meal item instead."
        ),
    )
    def update_food_tool(
        food_id: int,
        name: str | None = None,
        serving_size: Decimal | None = None,
        serving_unit: ServingUnit | None = None,
        calories: Decimal | None = None,
        protein_g: Decimal | None = None,
        carbs_g: Decimal | None = None,
        fat_g: Decimal | None = None,
        fiber_g: Decimal | None = None,
        sat_fat_g: Decimal | None = None,
        sodium_mg: Decimal | None = None,
        density_g_per_ml: Decimal | None = None,
    ) -> UpdateFoodResult:
        try:
            result = cast(
                UpdateFoodDomainResult,
                run_with_session(
                    update_food,
                    food_id=food_id,
                    name=name,
                    serving_size=serving_size,
                    serving_unit=serving_unit,
                    calories=calories,
                    protein_g=protein_g,
                    carbs_g=carbs_g,
                    fat_g=fat_g,
                    fiber_g=fiber_g,
                    sat_fat_g=sat_fat_g,
                    sodium_mg=sodium_mg,
                    density_g_per_ml=density_g_per_ml,
                ),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return {
            "food": FoodResponse.model_validate(result.food).model_dump(mode="json"),
            "recompute_count": result.affected_meals_count,
        }

    @mcp.tool(
        name="create_template",
        description="Create a reusable meal template. Use only for user-requested recurring meals.",
    )
    def create_template_tool(name: str, items: list[TemplateItemInput]) -> TemplateResult:
        specs = [TemplateItemSpec(**item.model_dump()) for item in items]
        try:
            template = cast(
                TemplateResponse,
                run_with_session(create_template, name=name, items=specs),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_template(template)

    @mcp.tool(
        name="update_template",
        description=(
            "Update a template for future use. Historical meals created from this template "
            "do not change."
        ),
    )
    def update_template_tool(
        template_id: int,
        name: str | None = None,
        items: list[TemplateItemInput] | None = None,
    ) -> TemplateResult:
        specs = [TemplateItemSpec(**item.model_dump()) for item in items] if items else None
        try:
            template = cast(
                TemplateResponse,
                run_with_session(
                    update_template,
                    template_id=template_id,
                    name=name,
                    items=specs,
                ),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_template(template)

    @mcp.tool(
        name="delete_template",
        description="Soft-delete a template. Existing meals logged from it remain unchanged.",
    )
    def delete_template_tool(template_id: int) -> TemplateResult:
        try:
            template = cast(
                TemplateResponse,
                run_with_session(delete_template, template_id=template_id),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_template(template)

    @mcp.tool(
        name="set_target",
        description="Insert a new target version effective on a date token or ISO date.",
    )
    def set_target_tool(
        base_calories: int,
        protein_g: int,
        carbs_g: int,
        fat_g: int,
        effective_from: str,
        local_tz: str,
    ) -> SetTargetResult:
        day = resolve_date_arg(effective_from, local_tz=local_tz)
        try:
            result = cast(
                SetTargetDto,
                run_with_session(
                    set_target,
                    base_calories=base_calories,
                    protein_g=protein_g,
                    carbs_g=carbs_g,
                    fat_g=fat_g,
                    effective_from=day,
                ),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_set_target_result(result)

    @mcp.tool(
        name="set_favorite_food",
        description="Mark or unmark a food as favorite to improve future food resolution.",
    )
    def set_favorite_food_tool(food_id: int, is_favorite: bool) -> AddFoodResult:
        try:
            food = run_with_session(
                set_favorite_food,
                food_id=food_id,
                is_favorite=is_favorite,
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return FoodResponse.model_validate(food)

    @mcp.tool(name="delete_meal", description="Hard-delete a meal and its meal items.")
    def delete_meal_tool(meal_id: int) -> DeleteResult:
        try:
            result = cast(dict[str, bool], run_with_session(delete_meal, meal_id=meal_id))
        except DomainError as exc:
            return capture_domain_error(exc)
        return DeleteResultModel(**result)

    @mcp.tool(name="delete_meal_item", description="Hard-delete one meal item.")
    def delete_meal_item_tool(item_id: int) -> DeleteResult:
        try:
            result = cast(
                dict[str, bool],
                run_with_session(delete_meal_item, item_id=item_id),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return DeleteResultModel(**result)

    @mcp.tool(
        name="update_meal",
        description=(
            "Fix one field on an already-logged meal (meal_type, logged_at, or notes) "
            "without touching its items. Use this instead of delete_meal + log_meal to "
            "correct one field — that round trip risks a ghost meal if the delete races "
            "or is forgotten. This never adds, removes, or edits items; use "
            "update_meal_item or delete_meal_item for that."
        ),
    )
    def update_meal_tool(
        meal_id: int,
        meal_type: MealType | None = None,
        logged_at: datetime | None = None,
        notes: str | None = _NOTES_UNSET,  # type: ignore[assignment]
    ) -> UpdateMealResult:
        domain_kwargs: dict[str, object] = {
            "meal_id": meal_id,
            "meal_type": meal_type,
            "logged_at": logged_at,
        }
        if notes is not _NOTES_UNSET:
            domain_kwargs["notes"] = notes
        try:
            meal = cast(
                MealResponse,
                run_with_session(update_meal, **domain_kwargs),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_meal(meal)

    @mcp.tool(
        name="update_meal_item",
        description=(
            "Fix one field on a single meal item: quantity, quantity_unit, food_id, or "
            "(ad-hoc items only) macros. Use this instead of delete_meal_item + re-logging "
            "an item to correct one field. Edits are local to this item only — they never "
            "rewrite other meals; use update_food when the correction should propagate "
            "everywhere that food is logged. Macro fields are rejected while food_id is "
            "set (that item computes macros live); clear food_id to null to make it "
            "ad-hoc, supplying calories/protein_g/carbs_g/fat_g in the same call."
        ),
    )
    def update_meal_item_tool(
        item_id: int,
        quantity: Decimal | None = None,
        quantity_unit: QuantityUnit | None = None,
        food_id: int | None = _FOOD_ID_UNSET,  # type: ignore[assignment]
        calories: Decimal | None = None,
        protein_g: Decimal | None = None,
        carbs_g: Decimal | None = None,
        fat_g: Decimal | None = None,
        fiber_g: Decimal | None = None,
        sat_fat_g: Decimal | None = None,
        sodium_mg: Decimal | None = None,
    ) -> UpdateMealItemResult:
        domain_kwargs: dict[str, object] = {
            "item_id": item_id,
            "quantity": quantity,
            "quantity_unit": quantity_unit,
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "fiber_g": fiber_g,
            "sat_fat_g": sat_fat_g,
            "sodium_mg": sodium_mg,
        }
        if food_id is not _FOOD_ID_UNSET:
            domain_kwargs["food_id"] = food_id
        try:
            item = cast(
                MealItemResponse,
                run_with_session(update_meal_item, **domain_kwargs),
            )
        except DomainError as exc:
            return capture_domain_error(exc)
        return serialize_meal_item(item)
