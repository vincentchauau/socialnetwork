"""The result tables of the old 4-role game are upgraded in place, idempotently, and old rows still read."""
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from sn_shared import directory
from sn_shared.directory import Person

from api.werewolf.history import list_history, save_record
from api.werewolf.db import Base
from api.werewolf.migrate import ensure_columns, merge_legacy_tables
from api.werewolf.models import FINISHED, LIVE, Game
from api.werewolf.rooms import GameRecord, PlayerRecord
from tests.werewolf.conftest import make_client

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
    assert sorted(added) == ["game_players.days_survived", "game_players.outcome", "game_results.size"]
    assert {"outcome", "days_survived"} <= columns(engine, "game_players")
    assert not {"username", "faction", "ability"} & columns(engine, "game_players")
    assert "size" in columns(engine, "game_results")
    assert ensure_columns(engine) == []  # idempotent
    with engine.connect() as conn:  # old rows got the defaults
        assert conn.execute(text("SELECT outcome, days_survived FROM game_players WHERE id = 1")).one() == ("", 0)
        assert conn.execute(text("SELECT size FROM game_results WHERE id = 1")).scalar() == 0


def test_ensure_columns_on_an_empty_database_is_a_noop():
    engine = create_engine("sqlite://")
    assert ensure_columns(engine) == []


def test_old_rows_are_still_readable_after_the_upgrade(old_db):
    _, engine = old_db
    ensure_columns(engine)
    Base.metadata.create_all(engine)
    merge_legacy_tables(engine)
    with sessionmaker(engine)() as session:
        directory.ensure_table_for_sqlite(engine)
        session.add_all([Person(user_id=7, username="alice"), Person(user_id=8, username="bob")])
        session.commit()
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
    with make_client(url) as client:
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


def test_rows_with_faction_and_ability_columns_are_folded_into_the_role_code(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mid.db'}")
    with engine.begin() as conn:
        for statement in OLD_SCHEMA[:2]:
            conn.execute(text(statement))
        conn.execute(text("ALTER TABLE game_players ADD COLUMN faction VARCHAR(16) NOT NULL DEFAULT ''"))
        conn.execute(text("ALTER TABLE game_players ADD COLUMN ability VARCHAR(24) NOT NULL DEFAULT ''"))
        conn.execute(text("INSERT INTO game_results VALUES (1, 'r', 'WOLF', 3, '2024-01-01 10:00:00')"))
        conn.execute(text("INSERT INTO game_players (id, result_id, user_id, username, role, survived, faction, ability)"
                          " VALUES (1, 1, 7, 'alice', 'WOLF', 1, 'WOLF', 'KILL')"))
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE game_players ADD COLUMN outcome VARCHAR(8) NOT NULL DEFAULT 'won'"))  # a row counts once its outcome is set
    ensure_columns(engine)  # folds the two columns into the code and, in SQLite, drops them
    with engine.connect() as conn:
        assert conn.execute(text("SELECT role FROM game_players")).scalar() == "W:K"
    assert {"faction", "ability"}.isdisjoint(c["name"] for c in inspect(engine).get_columns("game_players"))


def test_the_three_old_tables_are_copied_into_games_once(old_db):
    _, engine = old_db
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE ww_snapshots (code VARCHAR(16) PRIMARY KEY, data BLOB NOT NULL, saved_at DATETIME NOT NULL)"))
        conn.execute(text("INSERT INTO ww_snapshots VALUES ('LIVE1', X'0102', '2024-02-01 10:00:00')"))
    ensure_columns(engine)
    Base.metadata.create_all(engine)
    assert merge_legacy_tables(engine) == 3  # two finished games and one saved room
    assert merge_legacy_tables(engine) == 0  # a second start copies nothing
    with sessionmaker(engine)() as session:
        finished = session.scalars(select(Game).where(Game.status == FINISHED).order_by(Game.id)).all()
        live = session.scalars(select(Game).where(Game.status == LIVE)).all()
        assert [(g.room_code, g.player_ids, [p["user_id"] for p in g.players]) for g in finished] == [("oldroom", "|7|8|", [7, 8]), ("oldtwo", "|7|", [7])]
        assert [(g.room_code, g.state) for g in live] == [("LIVE1", b"")]
