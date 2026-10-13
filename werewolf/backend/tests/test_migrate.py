"""The result tables of the old 4-role game are upgraded in place, idempotently, and old rows still read."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.history import list_history, save_record
from app.main import create_app
from app.migrate import ensure_columns
from app.rooms import GameRecord, PlayerRecord

OLD_SCHEMA = [
    "CREATE TABLE game_results (id INTEGER PRIMARY KEY, room_id VARCHAR(32) NOT NULL, winner VARCHAR(16) NOT NULL,"
    " days INTEGER NOT NULL, finished_at DATETIME NOT NULL)",
    "CREATE TABLE game_players (id INTEGER PRIMARY KEY, result_id INTEGER NOT NULL REFERENCES game_results(id),"
    " user_id INTEGER NOT NULL, username VARCHAR(32) NOT NULL, role VARCHAR(16) NOT NULL, survived BOOLEAN NOT NULL)",
    "INSERT INTO game_results VALUES (1, 'oldroom', 'wolves', 3, '2024-01-01 10:00:00')",
    "INSERT INTO game_results VALUES (2, 'oldtwo', 'village', 2, '2024-01-02 10:00:00')",
    "INSERT INTO game_players VALUES (1, 1, 7, 'alice', 'werewolf', 1)",
    "INSERT INTO game_players VALUES (2, 1, 8, 'bob', 'seer', 0)",
    "INSERT INTO game_players VALUES (3, 2, 7, 'alice', 'doctor', 1)",
]


@pytest.fixture
def old_db(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:
        for statement in OLD_SCHEMA:
            conn.execute(text(statement))
    yield url, engine
    engine.dispose()


def columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_ensure_columns_adds_the_new_columns_once(old_db):
    _, engine = old_db
    added = ensure_columns(engine)
    assert sorted(added) == ["game_players.ability", "game_players.days_survived", "game_players.faction",
                             "game_players.outcome", "game_results.size"]
    assert {"faction", "ability", "outcome", "days_survived"} <= columns(engine, "game_players")
    assert "size" in columns(engine, "game_results")
    assert ensure_columns(engine) == []  # idempotent
    with engine.connect() as conn:  # old rows got the defaults
        assert conn.execute(text("SELECT faction, outcome, days_survived FROM game_players WHERE id = 1")).one() == ("", "", 0)
        assert conn.execute(text("SELECT size FROM game_results WHERE id = 1")).scalar() == 0


def test_ensure_columns_on_an_empty_database_is_a_noop():
    engine = create_engine("sqlite://")
    assert ensure_columns(engine) == []


def test_old_rows_are_still_readable_after_the_upgrade(old_db):
    _, engine = old_db
    ensure_columns(engine)
    with sessionmaker(engine)() as session:
        alice = {e.room_id: e for e in list_history(session, 7, 10)}
        bob = list_history(session, 8, 10)[0]
    wolf_game, village_game = alice["oldroom"], alice["oldtwo"]
    assert (wolf_game.winner, wolf_game.your_faction, wolf_game.your_outcome, wolf_game.won) == ("WOLF", "WOLF", "won", True)
    assert wolf_game.your_ability == "KILL" and wolf_game.size == 2 and wolf_game.survived
    assert (village_game.winner, village_game.your_faction, village_game.your_outcome) == ("VILLAGER", "VILLAGER", "won")
    assert (bob.your_faction, bob.your_ability, bob.your_outcome, bob.survived) == ("VILLAGER", "SEE_FACTION", "lost", False)
    assert [p.username for p in wolf_game.players] == ["alice", "bob"]


def test_the_app_upgrades_an_old_database_on_startup_and_stores_new_games(old_db):
    url, engine = old_db
    with TestClient(create_app(url)) as client:
        assert "outcome" in columns(engine, "game_players")
        factory = client.app.state.session_factory
        record = GameRecord("NEWRM", "GHOST", 4, 12, (PlayerRecord(7, "alice", "GHOST", "TRANSFORM", "won", True, 4),))
        assert save_record(factory, record)
        with factory() as session:
            newest = list_history(session, 7, 10)[0]
    assert (newest.room_id, newest.winner, newest.your_faction, newest.your_outcome, newest.days_survived) == \
        ("NEWRM", "GHOST", "GHOST", "won", 4)


def test_save_record_ignores_bots_and_survives_a_broken_database():
    engine = create_engine("sqlite://")
    factory = sessionmaker(engine)
    bots_only = GameRecord("BOTSX", "WOLF", 1, 5, (PlayerRecord(0, "x", "WOLF", "KILL", "won", True, 1),
                                                 PlayerRecord(-3, "y", "WOLF", "KILL", "won", True, 1)))
    assert save_record(factory, bots_only) is True  # nothing to store, no table needed
    assert save_record(factory, GameRecord("NOPEX", "WOLF", 1, 5, ())) is True
    human = GameRecord("HUMAN", "WOLF", 1, 5, (PlayerRecord(5, "a", "WOLF", "KILL", "won", True, 1),))
    assert save_record(factory, human) is False  # no tables: reported, never raised
