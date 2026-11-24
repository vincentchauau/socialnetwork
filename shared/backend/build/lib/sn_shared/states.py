"""The steps a thing goes through (an order, an application...): which step may follow which.

    ORDER = Transitions({"pending": ["paid", "cancelled"], "paid": ["shipped"], "shipped": [], "cancelled": []})
    ORDER.check("pending", "shipped", "the order")   # 409: Cannot move the order from pending to shipped
"""

from collections.abc import Iterable, Mapping

from fastapi import HTTPException, status


class Transitions:
    def __init__(self, table: Mapping[str, Iterable[str]]) -> None:
        self._table = {state: frozenset(targets) for state, targets in table.items()}

    @property
    def states(self) -> frozenset[str]:
        return frozenset(self._table)

    def next(self, state: str) -> frozenset[str]:
        """The steps that may follow `state` (none for an unknown state)."""
        return self._table.get(state, frozenset())

    def allows(self, current: str, target: str) -> bool:
        return target in self.next(current)

    def is_final(self, state: str) -> bool:
        return not self.next(state)

    def check(self, current: str, target: str, what: str = "it") -> None:
        """Raise 409 unless `target` may follow `current`."""
        if not self.allows(current, target):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot move {what} from {current} to {target}")
