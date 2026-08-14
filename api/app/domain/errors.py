"""Domain exception hierarchy used by API and MCP adapters.

Every Appendix C error code maps to exactly one subclass of :class:`DomainError`.
Transport adapters translate these into HTTP status codes or MCP tool errors.
"""

from __future__ import annotations


class DomainError(ValueError):
    """Base domain error carrying the machine-readable Appendix C code."""

    def __init__(
        self,
        *,
        error: str,
        message: str,
        candidates: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.candidates = candidates


# --- Authentication --------------------------------------------------------


class UnauthorizedError(DomainError):
    """Request lacks valid credentials."""

    def __init__(self, message: str = "Valid credentials are required.") -> None:
        super().__init__(error="unauthorized", message=message)


# --- Food errors -----------------------------------------------------------


class FoodNotFoundError(DomainError):
    """No food could be resolved and no ad-hoc macros were supplied."""

    def __init__(self, name: str) -> None:
        super().__init__(
            error="food_not_found",
            message=f"No foods match '{name}'. Provide macros to log an ad-hoc item.",
        )


class AdhocItemNameRequiredError(DomainError):
    """An ad-hoc item (food_id is None) was given no name.

    Food-linked items can fall back to the resolved food's current name, but
    an ad-hoc item has no other source of a name, so omitting it is rejected
    here rather than left to fail an opaque NOT NULL constraint at write time.
    """

    def __init__(self) -> None:
        super().__init__(
            error="adhoc_item_name_required",
            message="An ad-hoc item (no food_id) requires a name.",
        )


class FoodAmbiguousError(DomainError):
    """More than one candidate matched and no tie-breaker rule selected one."""

    def __init__(self, name: str, candidates: list[dict[str, object]]) -> None:
        super().__init__(
            error="food_ambiguous",
            message=f"Multiple foods match '{name}'. Specify one.",
            candidates=candidates,
        )


class FoodDuplicateError(DomainError):
    """add_food name collision without force: true."""

    def __init__(self, name: str, candidates: list[dict[str, object]]) -> None:
        super().__init__(
            error="food_duplicate",
            message=f"A food similar to '{name}' already exists. Use force to override.",
            candidates=candidates,
        )


class ServingUnitImmutableError(DomainError):
    """update_food attempt to change serving_unit."""

    def __init__(self) -> None:
        super().__init__(
            error="serving_unit_immutable",
            message="Cannot change serving_unit. Create a new food instead.",
        )


class FoodMergeSameFoodError(DomainError):
    """merge_food called with from_id == into_id."""

    def __init__(self, food_id: int) -> None:
        super().__init__(
            error="food_merge_same_food",
            message=f"Cannot merge food {food_id} into itself.",
        )


# --- Meal errors -----------------------------------------------------------


class MealNotFoundError(DomainError):
    """No meal exists with the given ID."""

    def __init__(self, meal_id: int) -> None:
        super().__init__(
            error="meal_not_found",
            message=f"Meal {meal_id} not found.",
        )


class MealItemNotFoundError(DomainError):
    """No meal item exists with the given ID."""

    def __init__(self, item_id: int) -> None:
        super().__init__(
            error="meal_item_not_found",
            message=f"Meal item {item_id} not found.",
        )


class MealItemFoodLinkedError(DomainError):
    """update_meal_item attempt to edit macros on a food-linked item.

    Food-linked items compute macros live from the referenced food and must
    stay NULL in storage (the ``adhoc_macros`` CHECK). Edit the food itself, or
    clear ``food_id`` (supplying all required macros) to make the item ad-hoc.
    """

    def __init__(self, item_id: int) -> None:
        super().__init__(
            error="meal_item_food_linked",
            message=(
                f"Meal item {item_id} is linked to a food and computes macros live; "
                "macro fields cannot be edited directly while food_id is set."
            ),
        )


class MealItemMacrosRequiredError(DomainError):
    """update_meal_item cleared food_id without supplying the now-required macros."""

    def __init__(self, item_id: int, missing_fields: list[str]) -> None:
        joined = ", ".join(missing_fields)
        super().__init__(
            error="meal_item_macros_required",
            message=(
                f"Meal item {item_id} is becoming ad-hoc (food_id cleared) and requires "
                f"calories, protein_g, carbs_g, and fat_g. Missing: {joined}."
            ),
        )


# --- Timezone errors --------------------------------------------------------


class InvalidTimezoneError(DomainError):
    """An explicit/effective-default local_tz or a settings update isn't a valid IANA name."""

    def __init__(self, tz: str) -> None:
        super().__init__(
            error="invalid_timezone",
            message=f"'{tz}' is not a valid IANA timezone name.",
        )


# --- Template errors -------------------------------------------------------


class TemplateNotFoundError(DomainError):
    """Template could not be found by id or name."""

    def __init__(self, identifier: str | int) -> None:
        super().__init__(
            error="template_not_found",
            message=f"No template found for '{identifier}'.",
        )


# --- External integrations -------------------------------------------------


class IntervalsUnavailableError(DomainError):
    """intervals.icu sync failed or is unreachable."""

    def __init__(self, message: str = "intervals.icu sync failed.") -> None:
        super().__init__(error="intervals_unavailable", message=message)


# --- Energy balance errors --------------------------------------------------


class NoTargetSetError(DomainError):
    """compute_energy_timeline was asked for a day with no effective target.

    Unlike ``get_day``, which tolerates a missing target by leaving
    ``effective_target``/``delta_vs_target`` as ``None`` on its response, the
    energy timeline's basal-drain line (§5 step 1) has no way to compute a
    per-minute drain rate without a ``base_calories`` figure to divide by
    1440 -- there's no sensible partial timeline to return. Routes/MCP tools
    (EC-08, not built yet) are expected to catch this and render the "no
    target set" empty state the spec (§8) describes, mirroring how
    ``SummaryRow`` already handles a missing target on the frontend.
    """

    def __init__(self, day: object) -> None:
        super().__init__(
            error="no_target_set",
            message=f"No target is set for {day}.",
        )


# --- Planned workout errors -------------------------------------------------


class NaiveDatetimeError(DomainError):
    """A caller-supplied timestamp field is missing a UTC offset.

    See docs/backlog.md KI-001: `meal_logging.log_meal`'s equivalent check
    raises a bare `ValueError`, which surfaces as an unhandled 500 instead of
    a 4xx. New call sites (e.g. `create_manual_planned_workout`) should raise
    this `DomainError` subclass instead so the mapping in `app/main.py`'s
    `ERROR_STATUS_BY_CODE` turns it into a proper 422.
    """

    def __init__(self, field: str) -> None:
        super().__init__(
            error="naive_datetime",
            message=f"'{field}' must be timezone-aware (include a UTC offset).",
        )
