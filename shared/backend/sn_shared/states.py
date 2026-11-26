"""The steps a thing goes through (an order, an application...): which step may follow which.

    ORDER = Transitions({"pending": ["paid", "cancelled"], "paid": ["shipped"], "shipped": [], "cancelled": []})
    ORDER.check("pending", "shipped", "the order")   # 409: Cannot move the order from pending to shipped
"""

from collections.abc import Iterable, Mapping

from fastapi import HTTPException, status

import logging
logger = logging.getLogger(__name__)


class Transitions:
    def __init__(self, table: Mapping[str, Iterable[str]]) -> None:
        try:
            self._table = {state: frozenset(targets) for state, targets in table.items()}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    @property
    def states(self) -> frozenset[str]:
        try:
            return frozenset(self._table)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("states failed")
            raise

    def next(self, state: str) -> frozenset[str]:
        """The steps that may follow `state` (none for an unknown state)."""
        try:
            return self._table.get(state, frozenset())
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("next failed")
            raise

    def allows(self, current: str, target: str) -> bool:
        try:
            return target in self.next(current)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("allows failed")
            raise

    def is_final(self, state: str) -> bool:
        try:
            return not self.next(state)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("is_final failed")
            raise

    def check(self, current: str, target: str, what: str = "it") -> None:
        """Raise 409 unless `target` may follow `current`."""
        try:
            if not self.allows(current, target):
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot move {what} from {current} to {target}")
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("check failed")
            raise
