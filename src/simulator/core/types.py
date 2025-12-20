"""Type definitions for the simulator core."""

from typing import List, TypedDict, Union


class ChangeDict(TypedDict):
    """Represents a state change from one value to another."""

    attribute: str
    before: Union[str, List[str], None]
    after: Union[str, List[str], None]
    kind: str  # "value", "trend", "narrowing", "constraint"
