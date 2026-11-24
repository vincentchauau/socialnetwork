"""The wallet, the spin, the history and the board of the roulette."""

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.roulette import game
from api.roulette.db import get_db
from sn_shared import directory
from api.roulette.models import START_CHIPS, Spin, Wallet
from api.roulette.schemas import LeaderOut, NumberCount, SpinIn, SpinOut, StatsOut, WalletOut
from sn_shared.limits import reader, writer
from sn_shared.security import TokenPayload

router = APIRouter()

HISTORY_LIMIT = 50
BOARD_SIZE = 10
STATS_DEFAULT = 100
STATS_MAX = 1000
STATS_TOP = 5


def _wallet(db: Session, user: TokenPayload, lock: bool = False) -> Wallet:
    query = select(Wallet).where(Wallet.user_id == user.user_id)
    if lock:
        query = query.with_for_update()  # two spins at once cannot spend the same chips
    wallet = db.scalars(query).first()
    if wallet is None:
        wallet = Wallet(user_id=user.user_id, chips=START_CHIPS)
        db.add(wallet)
        db.flush()
    return wallet


@router.get("/wallet", response_model=WalletOut)
def read_wallet(user: TokenPayload = Depends(reader), db: Session = Depends(get_db)) -> WalletOut:
    wallet = _wallet(db, user)
    db.commit()
    return WalletOut(chips=wallet.chips)


@router.post("/wallet/refill", response_model=WalletOut)
def refill(user: TokenPayload = Depends(writer), db: Session = Depends(get_db)) -> WalletOut:
    """A person with no chips left starts again with the first amount."""
    wallet = _wallet(db, user, lock=True)
    if wallet.chips > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "You still have chips")
    wallet.chips = START_CHIPS
    db.commit()
    return WalletOut(chips=wallet.chips)


@router.post("/spin", response_model=SpinOut, status_code=status.HTTP_201_CREATED)
def spin(body: SpinIn, user: TokenPayload = Depends(writer), db: Session = Depends(get_db)) -> Spin:
    stake = sum(bet.amount for bet in body.bets)
    wallet = _wallet(db, user, lock=True)
    if stake > wallet.chips:
        raise HTTPException(status.HTTP_409_CONFLICT, "Not enough chips")
    number = game.spin()
    bets = [
        {"kind": bet.kind, "pick": bet.pick, "amount": bet.amount, "payout": game.payout(bet.kind, bet.pick, bet.amount, number)}
        for bet in body.bets
    ]
    returned = sum(bet["payout"] for bet in bets)
    wallet.chips = wallet.chips - stake + returned
    record = Spin(
        user_id=user.user_id, number=number, bets=bets,
        stake=stake, payout=returned, balance_after=wallet.chips,
    )
    db.add(record)
    db.commit()
    return record


@router.get("/spins", response_model=list[SpinOut])
def history(user: TokenPayload = Depends(reader), db: Session = Depends(get_db)) -> list[Spin]:
    return list(db.scalars(select(Spin).where(Spin.user_id == user.user_id).order_by(Spin.id.desc()).limit(HISTORY_LIMIT)))


@router.delete("/spins/{spin_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_spin(spin_id: int, user: TokenPayload = Depends(writer), db: Session = Depends(get_db)) -> Response:
    record = db.get(Spin, spin_id)
    if record is None or record.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")  # 404, not 403: do not reveal the spins of others
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/spins", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(user: TokenPayload = Depends(writer), db: Session = Depends(get_db)) -> Response:
    for record in db.scalars(select(Spin).where(Spin.user_id == user.user_id)):
        db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stats", response_model=StatsOut)
def stats(
    last: int = Query(STATS_DEFAULT, ge=1, le=STATS_MAX),
    user: TokenPayload = Depends(reader),
    db: Session = Depends(get_db),
) -> StatsOut:
    """Which numbers came most and least often in the last spins of the person."""
    numbers = list(db.scalars(select(Spin.number).where(Spin.user_id == user.user_id).order_by(Spin.id.desc()).limit(last)))
    counts = Counter(numbers)
    rows = [NumberCount(number=n, colour=game.colour(n), count=counts.get(n, 0)) for n in range(game.POCKETS)]
    hot = sorted((row for row in rows if row.count > 0), key=lambda row: (-row.count, row.number))[:STATS_TOP]
    cold = sorted(rows, key=lambda row: (row.count, row.number))[:STATS_TOP] if numbers else []
    return StatsOut(spins=len(numbers), hot=hot, cold=cold)


@router.get("/board", response_model=list[LeaderOut])
def board(user: TokenPayload = Depends(reader), db: Session = Depends(get_db)) -> list[Wallet]:
    wallets = list(db.scalars(select(Wallet).order_by(Wallet.chips.desc(), Wallet.user_id).limit(BOARD_SIZE)))
    return directory.attach_names(db, wallets)  # one lookup for the whole board
