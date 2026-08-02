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
