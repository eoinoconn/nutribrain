"""Domain helpers and business rules.

The HTTP and MCP adapters call functions in this package so product rules are
implemented in one place.
"""

from app.domain.nutrition import (
    ItemMacros,
    UnitNormalizationError,
    compute_item_macros,
    normalize_to_grams,
)

__all__ = [
    "ItemMacros",
    "UnitNormalizationError",
    "compute_item_macros",
    "normalize_to_grams",
]
