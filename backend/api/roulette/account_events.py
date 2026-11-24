"""Reactions to account events published by `center` (delivered at least once).

Data model: `roulette_wallets` (user_id, chips) and `roulette_spins` (user_id, the bets and what they paid).

Deletion: the wallet and the spins of the user are deleted (play money, nothing others depend on).
Rename: nothing to do (the board reads names from `users`).
Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.roulette.models import Spin, Wallet


def on_user_deleted(db: Session, user_id: int) -> None:
    db.execute(delete(Spin).where(Spin.user_id == user_id))
    db.execute(delete(Wallet).where(Wallet.user_id == user_id))


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    """Nothing to do: wallets keep no name."""
