from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sn_shared import tags
from sn_shared.access import is_owner, ensure_owner
from sn_shared.db import make_engine
from sn_shared.states import Transitions


def test_a_stranger_gets_404_for_what_is_not_theirs_and_so_does_a_missing_thing():
    mine = SimpleNamespace(owner_id=1, seller_id=2)
    me = SimpleNamespace(user_id=1)
    assert ensure_owner(mine, me) is mine and is_owner(mine, 2, "seller_id")
    for thing in (mine, None):
        with pytest.raises(HTTPException) as caught:
            ensure_owner(thing, SimpleNamespace(user_id=9), what="Job not found")
        assert caught.value.status_code == 404 and caught.value.detail == "Job not found"
    assert is_owner(None, 1) is False


def test_which_step_may_follow_which_and_a_wrong_one_is_a_409():
    flow = Transitions({"new": ["open", "gone"], "open": ["done"], "done": [], "gone": []})
    assert flow.allows("new", "open") and not flow.allows("new", "done") and not flow.allows("nowhere", "open")
    assert flow.next("open") == {"done"} and flow.is_final("done") and flow.states == {"new", "open", "done", "gone"}
    flow.check("new", "gone")
    with pytest.raises(HTTPException) as caught:
        flow.check("new", "done", "the order")
    assert caught.value.status_code == 409 and caught.value.detail == "Cannot move the order from new to done"


def test_a_tag_is_trimmed_lowered_and_checked():
    assert tags.clean_tags([" Python ", "python", "C++", "ASP.NET", "machine learning"]) == ["python", "c++", "asp.net", "machine learning"]
    for bad in ("", "  ", "x" * 31, "a/b", "-x", "<b>"):
        with pytest.raises(ValueError):
            tags.clean_tag(bad)


def test_retire_columns_drops_a_legacy_column_of_an_old_sqlite_database_with_its_index():
    from sqlalchemy import inspect, text

    from sn_shared.db import make_engine, retire_columns

    engine = make_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE photos (id INTEGER PRIMARY KEY, user_id INTEGER, username VARCHAR(32) NOT NULL)"))
        conn.execute(text("CREATE INDEX ix_photos_username ON photos (username)"))
    assert retire_columns(engine, {"photos": ["username", "nothing"], "absent": ["x"]}) == ["photos.username"]
    assert {c["name"] for c in inspect(engine).get_columns("photos")} == {"id", "user_id"}
    assert retire_columns(engine, {"photos": ["username"]}) == []  # nothing left to do the second time
