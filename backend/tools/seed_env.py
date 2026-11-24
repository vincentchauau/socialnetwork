"""What every group of the seeder shares."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Engine

from tools.seed_cast import Cast

MAX_AGE_DAYS = 60


@dataclass
class Env:
    now: datetime
    rng: random.Random
    cast: Cast
    embedder: str
    engines: dict[str, Engine]

    def ago(self, days: float) -> datetime:
        """A moment `days` days before now (a few hours and minutes more, so rows made on one day do not share one time)."""
        days = max(0.0, min(float(days), MAX_AGE_DAYS))
        moment = self.now - timedelta(days=days, hours=self.rng.randint(0, 8), minutes=self.rng.randint(0, 59))
        return min(moment, self.now - timedelta(minutes=5))
