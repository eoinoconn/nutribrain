"""Domain exception hierarchy used by API and MCP adapters."""

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


class TemplateNotFoundError(DomainError):
    """Template could not be found by id or name."""

    def __init__(self, identifier: str | int) -> None:
        super().__init__(
            error="template_not_found",
            message=f"No template found for '{identifier}'.",
        )
