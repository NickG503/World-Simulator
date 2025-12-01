"""
Logical conditions module.

NOTE: Complex logical conditions (AND/OR/NOT/Implication) have been removed
as part of the tree-based simulation refactor.

Preconditions are now binary: single AttributeCondition that passes or fails.
Postconditions use flat if-elif-else structure in ConditionalEffects.
"""

from __future__ import annotations

# This module is kept for backward compatibility but is essentially empty.
# All condition logic now uses AttributeCondition directly.

__all__: list[str] = []
