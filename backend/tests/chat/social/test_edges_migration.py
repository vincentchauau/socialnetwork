"""`social_models.ensure_tables` fills `edges` from the three tables it replaced, once, and leaves the old tables alone."""

from sqlalchemy import create_engine, inspect, text

from api.chat.social import models as social_models

OLD_TABLES = (
    "CREATE TABLE social_relationships (requester_id INTEGER, addressee_id INTEGER, status VARCHAR(8), created_at DATETIME, updated_at DATETIME, PRIMARY KEY (requester_id, addressee_id))",
    "CREATE TABLE social_blocks (user_id INTEGER, blocked_id INTEGER, created_at DATETIME, PRIMARY KEY (user_id, blocked_id))",
    "CREATE TABLE social_companions (owner_id INTEGER, virtual_id INTEGER, created_at DATETIME, released_at DATETIME, PRIMARY KEY (owner_id, virtual_id))",
)


def edges(engine) -> set[tuple]:
    with engine.connect() as conn:
        return set(conn.execute(text("SELECT src_id, dst_id, kind, status, released_at FROM edges")).all())


def old_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        for ddl in OLD_TABLES:
            conn.execute(text(ddl))
        conn.execute(text("INSERT INTO social_relationships VALUES (1, 2, 'accepted', '2026-01-01', '2026-01-01'), (3, 1, 'pending', '2026-01-01', '2026-01-01'), (2, 4, 'declined', '2026-01-01', '2026-01-01')"))
        conn.execute(text("INSERT INTO social_blocks VALUES (5, 1, '2026-01-01')"))
        conn.execute(text("INSERT INTO social_companions VALUES (1, 70, '2026-01-01', NULL), (1, 71, '2026-01-01', '2026-02-01')"))
    return engine


def test_the_old_tables_are_copied_into_the_edges(tmp_path):
    engine = old_engine(tmp_path)
    social_models.ensure_tables(engine)
    assert {row[:4] for row in edges(engine)} == {
        (1, 2, "friend", "accepted"),
        (3, 1, "friend", "pending"),
        (2, 4, "friend", "declined"),
        (5, 1, "block", ""),
        (1, 70, "companion", ""),
        (1, 71, "companion", ""),
    }
    released = {row[1]: row[4] for row in edges(engine) if row[2] == "companion"}
    assert released[70] is None and released[71] is not None
    assert {"social_relationships", "social_blocks", "social_companions"} <= set(inspect(engine).get_table_names())  # left for the owner to drop


def test_the_copy_happens_only_while_the_edges_are_empty(tmp_path):
    engine = old_engine(tmp_path)
    social_models.ensure_tables(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM edges WHERE kind <> 'block'"))
        conn.execute(text("INSERT INTO social_blocks VALUES (9, 8, '2026-01-01')"))
    social_models.ensure_tables(engine)  # not empty: nothing is copied again
    assert {row[:3] for row in edges(engine)} == {(5, 1, "block")}


def test_a_fresh_database_has_no_old_tables_to_copy(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    social_models.ensure_tables(engine)
    social_models.ensure_tables(engine)
    assert edges(engine) == set()
    assert "social_relationships" not in inspect(engine).get_table_names()
