"""The ranking: who won most of the latest finished games."""

from sn_shared.testing import add_person

from api.werewolf.models import FINISHED, Game, ids_text
from api.werewolf.rolecode import role_code
from tests.werewolf.conftest import auth_cookie


def finished(client, results, winner="VILLAGER", at=None):
    """A finished game with one human player per (user id, outcome)."""
    entries = [{"user_id": uid, "role": role_code("VILLAGER", "NONE"), "outcome": outcome, "survived": True, "days_survived": 2} for uid, outcome in results]
    with client.app.state.session_factory() as db:
        db.add(Game(room_code="R" + str(len(entries)), status=FINISHED, winner=winner, days=2, size=6, players=entries, player_ids=ids_text(uid for uid, _ in results), finished_at=at))
        db.commit()


def people(client):
    for uid, name in ((1, "alice"), (2, "bob"), (3, "carol"), (4, "dan")):
        add_person(client.app.state.session_factory, uid, name)


def test_the_people_who_won_most_come_first_and_fewer_games_break_a_tie(client):
    people(client)
    finished(client, [(1, "won"), (2, "lost")])
    finished(client, [(1, "won"), (2, "lost"), (3, "won")])
    finished(client, [(2, "won"), (3, "lost")])
    finished(client, [(4, "lost"), (3, "lost")])  # a person who never won is not ranked
    board = client.get("/leaderboard", headers=auth_cookie()).json()
    assert [(row["username"], row["wins"], row["games"]) for row in board] == [("alice", 2, 2), ("bob", 1, 3), ("carol", 1, 3)]


def test_a_draw_is_not_a_win_and_the_ranking_holds_ten_at_most(client):
    for uid in range(1, 15):
        add_person(client.app.state.session_factory, uid, f"p{uid}")
        finished(client, [(uid, "won")])
    finished(client, [(1, "draw"), (2, "draw")], winner="DRAW")
    board = client.get("/leaderboard", headers=auth_cookie()).json()
    assert len(board) == 10
    assert all(row["wins"] == 1 for row in board)


def test_the_ranking_needs_a_session_and_is_empty_without_games(client):
    assert client.get("/leaderboard").status_code == 401
    assert client.get("/leaderboard", headers=auth_cookie()).json() == []


def test_a_season_counts_only_the_games_of_this_month(client):
    from datetime import timedelta
    from api.werewolf.history import season_start

    people(client)
    finished(client, [(1, "won"), (2, "lost")], at=season_start() - timedelta(days=3))  # last month
    finished(client, [(2, "won"), (1, "lost")], at=season_start() + timedelta(seconds=5))
    month = client.get("/leaderboard?season=month", headers=auth_cookie()).json()
    assert [(row["username"], row["wins"]) for row in month] == [("bob", 1)]
    assert len(client.get("/leaderboard", headers=auth_cookie()).json()) == 2
    assert client.get("/leaderboard?season=year", headers=auth_cookie()).status_code == 422
