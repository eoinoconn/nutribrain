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


# --- Settings errors ---------------------------------------------------------


class InvalidTimezoneError(DomainError):
    """update_settings received a value that isn't a valid IANA timezone name."""

    def __init__(self, local_timezone: str) -> None:
        super().__init__(
            error="invalid_timezone",
            message=f"'{local_timezone}' is not a valid IANA timezone name.",
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
