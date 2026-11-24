import pytest

from api.roulette import game


def test_the_wheel_has_18_red_18_black_and_one_green():
    colours = [game.colour(n) for n in range(37)]
    assert (colours.count("red"), colours.count("black"), colours.count("green")) == (18, 18, 1)


def test_the_ball_stops_on_a_pocket_in_range():
    seen = {game.spin() for _ in range(3000)}
    assert seen <= set(range(37)) and len(seen) > 30


@pytest.mark.parametrize(
    "kind,pick,number,expected",
    [
        ("straight", 17, 17, 36), ("straight", 17, 18, 0), ("straight", 0, 0, 36),
        ("red", None, 1, 2), ("red", None, 2, 0), ("black", None, 2, 2),
        ("odd", None, 7, 2), ("even", None, 8, 2), ("low", None, 18, 2), ("high", None, 19, 2),
        ("dozen", 1, 12, 3), ("dozen", 2, 13, 3), ("dozen", 3, 36, 3), ("dozen", 1, 13, 0),
        ("column", 1, 34, 3), ("column", 2, 2, 3), ("column", 3, 3, 3), ("column", 1, 2, 0),
        ("split", 506, 5, 18), ("split", 506, 6, 18), ("split", 506, 7, 0), ("split", 1, 0, 18), ("split", 1, 1, 18),
        ("street", 4, 6, 12), ("street", 4, 7, 0), ("corner", 5, 9, 9), ("corner", 5, 7, 0), ("line", 4, 9, 6), ("line", 4, 10, 0),
    ],
)
def test_what_each_bet_returns_for_a_stake_of_one(kind, pick, number, expected):
    assert game.payout(kind, pick, 1, number) == expected


@pytest.mark.parametrize("kind,pick", [("red", None), ("black", None), ("odd", None), ("even", None), ("low", None), ("high", None), ("dozen", 1), ("column", 1)])
def test_zero_loses_every_outside_bet(kind, pick):
    assert game.payout(kind, pick, 10, 0) == 0


def test_only_places_on_the_table_are_valid():
    good = [("split", 1), ("split", 102), ("split", 405), ("split", 2528), ("split", 3336), ("split", 3), ("street", 1), ("street", 34), ("corner", 1), ("corner", 32), ("line", 1), ("line", 31)]
    bad = [("split", 304), ("split", 3637), ("split", 105), ("split", 4), ("split", 0), ("street", 2), ("street", 37), ("corner", 3), ("corner", 33), ("line", 2), ("line", 34), ("split", None)]
    assert all(game.valid_pick(kind, pick) for kind, pick in good)
    assert not any(game.valid_pick(kind, pick) for kind, pick in bad)
