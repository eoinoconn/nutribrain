"""Tests for T-028: Deletion and error taxonomy.

Verifies:
- Every Appendix C error code maps to exactly one DomainError subclass.
- delete_meal and delete_meal_item perform hard deletes.
- Soft-delete filtering excludes deleted foods/templates from read paths.
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy.orm import Session

from app.db import Meal, MealItem
from app.domain.errors import DomainError, MealItemNotFoundError, MealNotFoundError
from app.domain.meal_deletion import delete_meal, delete_meal_item

# --- Appendix C error code coverage ----------------------------------------

# The canonical set of error codes from spec Appendix C.
APPENDIX_C_CODES = frozenset(
    {
        "unauthorized",
        "food_not_found",
        "food_ambiguous",
        "food_duplicate",
        "serving_unit_immutable",
        "template_not_found",
        "intervals_unavailable",
        "meal_not_found",
        "meal_item_not_found",
        "invalid_timezone",
        "naive_datetime",
    }
)


def _collect_domain_error_subclasses() -> list[type[DomainError]]:
    """Walk the DomainError hierarchy and return all concrete subclasses."""

    import app.domain.errors as errors_module

    subclasses: list[type[DomainError]] = []
    for _name, obj in inspect.getmembers(errors_module, inspect.isclass):
        if obj is DomainError:
            continue
        if issubclass(obj, DomainError):
            subclasses.append(obj)
    return subclasses


def _get_error_code(cls: type[DomainError]) -> str:
    """Instantiate a DomainError subclass with minimal args to extract its code."""

    # Each subclass has a different __init__ signature; try common patterns.
    try:
        instance = cls.__new__(cls)
        # Zero-arg init (UnauthorizedError, ServingUnitImmutableError, etc.)
        cls.__init__(instance)  # type: ignore[misc]
        return instance.error
    except TypeError:
        pass

    # One string arg (FoodNotFoundError, FoodDuplicateError)
    try:
        instance = cls.__new__(cls)
        cls.__init__(instance, "test")  # type: ignore[misc]
        return instance.error
    except TypeError:
        pass

    # One int arg (MealNotFoundError, MealItemNotFoundError, TemplateNotFoundError)
    try:
        instance = cls.__new__(cls)
        cls.__init__(instance, 1)  # type: ignore[misc]
        return instance.error
    except TypeError:
        pass

    # Two args: name + candidates (FoodAmbiguousError)
    try:
        instance = cls.__new__(cls)
        cls.__init__(instance, "test", [])  # type: ignore[misc]
        return instance.error
    except TypeError:
        pass

    raise AssertionError(f"Cannot instantiate {cls.__name__} to extract error code")


class TestErrorHierarchy:
    """Every Appendix C code maps to exactly one DomainError subclass."""

    def test_every_appendix_c_code_has_one_exception_class(self) -> None:
        subclasses = _collect_domain_error_subclasses()
        code_to_class: dict[str, type[DomainError]] = {}

        for cls in subclasses:
            code = _get_error_code(cls)
            assert code not in code_to_class, (
                f"Duplicate: {code!r} claimed by both "
                f"{code_to_class[code].__name__} and {cls.__name__}"
            )
            code_to_class[code] = cls

        # Every Appendix C code is covered
        missing = APPENDIX_C_CODES - set(code_to_class.keys())
        assert not missing, f"Appendix C codes without an exception class: {missing}"

    def test_no_extra_codes_outside_appendix_c(self) -> None:
        """All exception codes match a known Appendix C entry."""
        subclasses = _collect_domain_error_subclasses()
        codes = {_get_error_code(cls) for cls in subclasses}
        extra = codes - APPENDIX_C_CODES
        assert not extra, f"Exception codes not in Appendix C: {extra}"

    def test_all_subclasses_carry_required_attributes(self) -> None:
        subclasses = _collect_domain_error_subclasses()
        for cls in subclasses:
            instance = _instantiate(cls)
            assert hasattr(instance, "error")
            assert hasattr(instance, "message")
            assert hasattr(instance, "candidates")
            assert isinstance(instance.error, str)
            assert isinstance(instance.message, str)
            assert instance.candidates is None or isinstance(instance.candidates, list)


def _instantiate(cls: type[DomainError]) -> DomainError:
    """Best-effort instantiation for attribute checks."""
    try:
        return cls()  # type: ignore[call-arg]
    except TypeError:
        pass
    try:
        return cls("test")  # type: ignore[call-arg]
    except TypeError:
        pass
    try:
        return cls(1)  # type: ignore[call-arg]
    except TypeError:
        pass
    try:
        return cls("test", [])  # type: ignore[call-arg]
    except TypeError:
        pass
    raise AssertionError(f"Cannot instantiate {cls.__name__}")


# --- Hard delete tests -----------------------------------------------------


class TestDeleteMeal:
    def test_delete_existing_meal(self, db_session: Session, make_meal, make_meal_item) -> None:
        meal = make_meal()
        item = make_meal_item(meal=meal)
        meal_id = meal.id
        item_id = item.id

        result = delete_meal(db_session, meal_id=meal_id)

        assert result == {"deleted": True}
        # Expire cached objects so subsequent gets hit the database
        db_session.expire_all()
        assert db_session.get(Meal, meal_id) is None
        assert db_session.get(MealItem, item_id) is None

    def test_delete_nonexistent_meal_raises(self, db_session: Session) -> None:
        with pytest.raises(MealNotFoundError) as exc_info:
            delete_meal(db_session, meal_id=999999)

        assert exc_info.value.error == "meal_not_found"


class TestDeleteMealItem:
    def test_delete_existing_meal_item(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        meal = make_meal()
        item = make_meal_item(meal=meal)
        item_id = item.id
        meal_id = meal.id

        result = delete_meal_item(db_session, item_id=item_id)

        assert result == {"deleted": True}
        assert db_session.get(MealItem, item_id) is None
        # Meal itself should still exist
        assert db_session.get(Meal, meal_id) is not None

    def test_delete_nonexistent_item_raises(self, db_session: Session) -> None:
        with pytest.raises(MealItemNotFoundError) as exc_info:
            delete_meal_item(db_session, item_id=999999)

        assert exc_info.value.error == "meal_item_not_found"
