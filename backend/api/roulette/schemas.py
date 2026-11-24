from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.roulette.game import NUMBERED, SPLIT_KIND, valid_pick

MAX_BET = 500
MAX_BETS = 20

Kind = Literal["straight", "split", "street", "corner", "line", "red", "black", "odd", "even", "low", "high", "dozen", "column"]


class BetIn(BaseModel):
    kind: Kind
    pick: int | None = None  # the number (straight), or which dozen / column (1..3)
    amount: int = Field(ge=1, le=MAX_BET)

    @model_validator(mode="after")
    def check_pick(self) -> "BetIn":
        if self.kind in NUMBERED or self.kind == SPLIT_KIND:
            if not valid_pick(self.kind, self.pick):
                raise ValueError(f"A {self.kind} bet needs a place that is on the table")
        elif self.pick is not None:
            raise ValueError(f"A {self.kind} bet takes no pick")
        return self


class SpinIn(BaseModel):
    bets: list[BetIn] = Field(min_length=1, max_length=MAX_BETS)


class BetOut(BaseModel):
    kind: str
    pick: int | None
    amount: int
    payout: int


class SpinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    colour: str
    bets: list[BetOut]
    stake: int
    payout: int
    balance_after: int
    created_at: datetime


class WalletOut(BaseModel):
    chips: int
    max_bet: int = MAX_BET
    max_bets: int = MAX_BETS


class NumberCount(BaseModel):
    number: int
    colour: str
    count: int


class StatsOut(BaseModel):
    spins: int  # how many of the last spins were counted
    hot: list[NumberCount]  # the numbers that came most often
    cold: list[NumberCount]  # the ones that came least often (never included)


class LeaderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    chips: int
