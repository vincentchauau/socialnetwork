from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.roulette.db import Base
from api.roulette.game import colour
from sn_shared.clock import utcnow

START_CHIPS = 1000


class Wallet(Base):
    """The chips of a person (play money: nothing is bought or paid out)."""

    __tablename__ = "roulette_wallets"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    chips: Mapped[int] = mapped_column(BigInteger, default=START_CHIPS)


class Spin(Base):
    __tablename__ = "roulette_spins"
    __table_args__ = (Index("ix_roulette_spins_user", "user_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    bets: Mapped[list] = mapped_column(JSON)
    stake: Mapped[int] = mapped_column(BigInteger)
    payout: Mapped[int] = mapped_column(BigInteger)
    balance_after: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def colour(self) -> str:
        """The pocket colour: the number says it, so it is not stored."""
        return colour(self.number)
