"""The rules of European roulette (one zero), as pure functions: the wheel, the kinds of bet and what each pays."""

import secrets

POCKETS = 37  # 0..36
RED = frozenset({1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36})

# kind -> what it pays besides the stake
KINDS = {
    "straight": 35,
    "split": 17,
    "street": 11,
    "corner": 8,
    "line": 5,
    "red": 1,
    "black": 1,
    "odd": 1,
    "even": 1,
    "low": 1,
    "high": 1,
    "dozen": 2,
    "column": 2,
}
# kinds that name a number or a group, and the range of the pick
NUMBERED = {"straight": (0, 36), "dozen": (1, 3), "column": (1, 3), "street": (1, 34), "corner": (1, 32), "line": (1, 31)}
SPLIT_KIND = "split"  # the pick is the two numbers as low * 100 + high


def split_pair(pick: int) -> tuple[int, int]:
    return pick // 100, pick % 100


def valid_pick(kind: str, pick: int | None) -> bool:
    """Is `pick` a place on the table for this kind of bet? (a street starts a row of three, a corner is four that touch, ...)"""
    if pick is None:
        return False
    if kind == SPLIT_KIND:
        low, high = split_pair(pick)
        if low == 0:
            return high in (1, 2, 3)
        return 1 <= low < high <= 36 and (high - low == 3 or (high - low == 1 and low % 3 != 0))
    low, high = NUMBERED[kind]
    if not low <= pick <= high:
        return False
    if kind == "street":
        return pick % 3 == 1
    if kind == "corner":
        return pick % 3 != 0
    if kind == "line":
        return pick % 3 == 1
    return True


def spin() -> int:
    """The number the ball stops at; from the system's secure source, never from a seed a person could know."""
    return secrets.randbelow(POCKETS)


def colour(number: int) -> str:
    if number == 0:
        return "green"
    return "red" if number in RED else "black"


def wins(kind: str, pick: int | None, number: int) -> bool:
    if number == 0:
        # zero beats every outside bet; only a bet on the zero itself (alone or with a neighbour) wins
        return (kind == "straight" and pick == 0) or (kind == SPLIT_KIND and 0 in split_pair(pick or 0) and pick is not None and pick < 100)
    if kind == "straight":
        return pick == number
    if kind == SPLIT_KIND:
        return number in split_pair(pick or 0)
    if kind == "street":
        return pick is not None and pick <= number <= pick + 2
    if kind == "corner":
        return pick is not None and number in (pick, pick + 1, pick + 3, pick + 4)
    if kind == "line":
        return pick is not None and pick <= number <= pick + 5
    if kind in ("red", "black"):
        return colour(number) == kind
    if kind == "odd":
        return number % 2 == 1
    if kind == "even":
        return number % 2 == 0
    if kind == "low":
        return number <= 18
    if kind == "high":
        return number >= 19
    if kind == "dozen":
        return (number - 1) // 12 + 1 == pick
    if kind == "column":
        return (number - 1) % 3 + 1 == pick
    return False


def payout(kind: str, pick: int | None, amount: int, number: int) -> int:
    """What comes back to the player for one bet: the stake plus the win, or 0."""
    return amount * (KINDS[kind] + 1) if wins(kind, pick, number) else 0
