"""Templates domain (T-026).

CRUD operations for templates plus log_template which materializes a template
into a meal. Editing a template does NOT touch already-logged meals — those are
already materialized as independent meal_items rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import (
    Food,
    Meal,
    MealItem,
    MealItemSource,
    MealType,
    Template,
    TemplateItem,
)
from app.domain.dto import (
    ItemMacros,
    MealItemResponse,
    MealResponse,
    TemplateItemResponse,
    TemplateItemSpec,
    TemplateResponse,
)
from app.domain.errors import TemplateNotFoundError
from app.domain.meal_timing import resolve_meal_type
from app.domain.nutrition_math import compute_item_macros


def create_template(
    session: Session,
    *,
    name: str,
    items: list[TemplateItemSpec],
) -> TemplateResponse:
    """Create a new template with items.

    Items follow the same ad-hoc invariant as meal_items: food_id set means no
    stored macros; food_id NULL means macros are required.
    """

    template = Template(name=name)
    session.add(template)
    session.flush()

    for spec in items:
        ti = _spec_to_template_item(spec, template.id)
        session.add(ti)

    session.flush()
    session.refresh(template, ["items"])
    return _template_to_response(template)


def update_template(
    session: Session,
    *,
    template_id: int,
    name: str | None = None,
    items: list[TemplateItemSpec] | None = None,
) -> TemplateResponse:
    """Update a template's name and/or replace its items.

    Editing a template affects future applications only. Past meals logged from
    this template are already materialized as meal_items and are NOT recomputed.
    """

    template = _get_template_or_raise(session, template_id)

    if name is not None:
        template.name = name

    if items is not None:
        # Replace all items: delete existing, add new
        for existing_item in list(template.items):
            session.delete(existing_item)
        session.flush()

        for spec in items:
            ti = _spec_to_template_item(spec, template.id)
            session.add(ti)

    session.flush()
    session.refresh(template, ["items"])
    return _template_to_response(template)


def delete_template(
    session: Session,
    *,
    template_id: int,
) -> TemplateResponse:
    """Soft-delete a template. Past meal_items are unaffected."""

    template = _get_template_or_raise(session, template_id)
    template.deleted_at = datetime.now(UTC)
    session.flush()
    return _template_to_response(template)


def list_templates(session: Session, *, query: str = "") -> list[TemplateResponse]:
    """Return non-deleted templates, optionally filtered by name substring."""

    stmt = (
        select(Template)
        .where(Template.deleted_at.is_(None))
        .options(selectinload(Template.items))
        .order_by(Template.id)
    )

    lowered = query.strip().lower()
    if lowered:
        stmt = stmt.where(func.lower(Template.name).contains(lowered))

    templates = session.scalars(stmt).all()
    return [_template_to_response(t) for t in templates]


def log_template(
    session: Session,
    *,
    template_id: int,
    logged_at: datetime,
    local_tz: str,
    meal_type: str | None = None,
    quantity_scale: Decimal = Decimal("1"),
    notes: str | None = None,
) -> MealResponse:
    """Materialize a template into a meal.

    Each template_item becomes a meal_item:
    - food_id set → meal_item gets the same food_id; macros compute live (§3)
    - food_id NULL → template_item's estimate copies into the new meal_item
    - quantity from the template_item multiplied by quantity_scale
    - source: template on every resulting meal_item
    """

    if logged_at.tzinfo is None:
        raise ValueError("logged_at must be timezone-aware")

    template = _get_template_or_raise(session, template_id)

    # Derive local_date
    local_dt = logged_at.astimezone(ZoneInfo(local_tz))
    local_date = local_dt.date()

    # Resolve meal type
    meal_type_enum = resolve_meal_type(
        MealType(meal_type) if meal_type else None,
        logged_at,
        local_tz,
    )

    # Create the meal
    meal = Meal(
        logged_at=logged_at,
        local_tz=local_tz,
        local_date=local_date,
        meal_type=meal_type_enum,
        notes=notes,
    )
    session.add(meal)
    session.flush()

    # Materialize template items into meal items
    meal_items: list[MealItem] = []
    for ti in template.items:
        scaled_quantity = ti.quantity * quantity_scale

        if ti.food_id is not None:
            # Food-backed: no macros stored on the meal_item
            mi = MealItem(
                meal_id=meal.id,
                food_id=ti.food_id,
                name=ti.name,
                quantity=scaled_quantity,
                quantity_unit=ti.quantity_unit,
                source=MealItemSource.template,
            )
        else:
            # Ad-hoc: copy estimate macros (scaled by quantity_scale)
            mi = MealItem(
                meal_id=meal.id,
                food_id=None,
                name=ti.name,
                quantity=scaled_quantity,
                quantity_unit=ti.quantity_unit,
                calories=_scale_macro(ti.calories, quantity_scale),
                protein_g=_scale_macro(ti.protein_g, quantity_scale),
                carbs_g=_scale_macro(ti.carbs_g, quantity_scale),
                fat_g=_scale_macro(ti.fat_g, quantity_scale),
                fiber_g=_scale_macro(ti.fiber_g, quantity_scale),
                sat_fat_g=_scale_macro(ti.sat_fat_g, quantity_scale),
                sodium_mg=_scale_macro(ti.sodium_mg, quantity_scale),
                source=MealItemSource.template,
            )
        session.add(mi)
        meal_items.append(mi)

    session.flush()

    # Compute totals and build response
    total_calories = Decimal("0")
    total_protein_g = Decimal("0")
    total_carbs_g = Decimal("0")
    total_fat_g = Decimal("0")
    total_fiber_g = Decimal("0")
    total_sat_fat_g = Decimal("0")
    total_sodium_mg = Decimal("0")

    item_responses: list[MealItemResponse] = []
    for mi in meal_items:
        food: Food | None = None
        if mi.food_id is not None:
            food = session.get(Food, mi.food_id)
        macros = compute_item_macros(mi, food)

        total_calories += macros.calories
        total_protein_g += macros.protein_g
        total_carbs_g += macros.carbs_g
        total_fat_g += macros.fat_g
        if macros.fiber_g is not None:
            total_fiber_g += macros.fiber_g
        if macros.sat_fat_g is not None:
            total_sat_fat_g += macros.sat_fat_g
        if macros.sodium_mg is not None:
            total_sodium_mg += macros.sodium_mg

        item_responses.append(
            MealItemResponse(
                id=mi.id,
                food_id=mi.food_id,
                name=mi.name,
                quantity=mi.quantity,
                quantity_unit=mi.quantity_unit,
                source=mi.source,
                macros=macros,
            )
        )

    totals = ItemMacros(
        calories=total_calories,
        protein_g=total_protein_g,
        carbs_g=total_carbs_g,
        fat_g=total_fat_g,
        fiber_g=total_fiber_g if total_fiber_g else None,
        sat_fat_g=total_sat_fat_g if total_sat_fat_g else None,
        sodium_mg=total_sodium_mg if total_sodium_mg else None,
    )

    return MealResponse(
        id=meal.id,
        logged_at=meal.logged_at,
        local_tz=meal.local_tz,
        local_date=meal.local_date,
        meal_type=meal.meal_type,
        notes=meal.notes,
        items=item_responses,
        totals=totals,
        delta_vs_target=None,  # Template logging doesn't compute delta
    )


# --- Private helpers --------------------------------------------------------


def _get_template_or_raise(session: Session, template_id: int) -> Template:
    """Load a non-deleted template or raise TemplateNotFoundError."""

    stmt = (
        select(Template)
        .where(Template.id == template_id, Template.deleted_at.is_(None))
        .options(selectinload(Template.items))
    )
    template = session.scalar(stmt)
    if template is None:
        raise TemplateNotFoundError(template_id)
    return template


def _spec_to_template_item(spec: TemplateItemSpec, template_id: int) -> TemplateItem:
    """Convert a TemplateItemSpec to a TemplateItem ORM object."""

    if spec.food_id is not None:
        return TemplateItem(
            template_id=template_id,
            food_id=spec.food_id,
            name=spec.name,
            quantity=spec.quantity,
            quantity_unit=spec.quantity_unit,
        )
    return TemplateItem(
        template_id=template_id,
        food_id=None,
        name=spec.name,
        quantity=spec.quantity,
        quantity_unit=spec.quantity_unit,
        calories=spec.calories,
        protein_g=spec.protein_g,
        carbs_g=spec.carbs_g,
        fat_g=spec.fat_g,
        fiber_g=spec.fiber_g,
        sat_fat_g=spec.sat_fat_g,
        sodium_mg=spec.sodium_mg,
    )


def _scale_macro(value: Decimal | None, scale: Decimal) -> Decimal | None:
    """Scale a macro value by quantity_scale, preserving None."""

    if value is None:
        return None
    return value * scale


def _template_to_response(template: Template) -> TemplateResponse:
    """Convert a Template ORM object to a TemplateResponse DTO."""

    return TemplateResponse(
        id=template.id,
        name=template.name,
        created_at=template.created_at,
        deleted_at=template.deleted_at,
        items=[
            TemplateItemResponse(
                id=ti.id,
                food_id=ti.food_id,
                name=ti.name,
                quantity=ti.quantity,
                quantity_unit=ti.quantity_unit,
                calories=ti.calories,
                protein_g=ti.protein_g,
                carbs_g=ti.carbs_g,
                fat_g=ti.fat_g,
                fiber_g=ti.fiber_g,
                sat_fat_g=ti.sat_fat_g,
                sodium_mg=ti.sodium_mg,
            )
            for ti in template.items
        ],
    )
