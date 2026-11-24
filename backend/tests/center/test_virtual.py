"""Virtual people: they exist in `users`, share the namespace of names, and can never sign in."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from api.center.models import User
from api.center.sessions import begin_session, issue_session
from api.center.virtual import NameTaken, create_virtual
from tests.center.helpers import register


def make(client, name="Lan"):
    with client.app.state.session_factory() as db:
        user = create_virtual(db, name)
        db.commit()
        return user.id


def kinds(client):
    with client.app.state.session_factory() as db:
        return {u.username: u.kind for u in db.scalars(select(User))}


def test_a_virtual_person_is_a_user_of_its_own_kind_without_a_password(client):
    uid = make(client)
    with client.app.state.session_factory() as db:
        user = db.get(User, uid)
        assert (user.username, user.kind, user.group) == ("Lan", "virtual", "user")
        assert user.has_password is False and user.email is None and user.phone is None
    register(client)
    assert kinds(client) == {"Lan": "virtual", "Alice": "human"}  # a person who registers is `human`


def test_a_name_used_by_a_virtual_person_cannot_be_registered_and_the_other_way_round(client):
    make(client, "Lan")
    taken = client.post("/auth/register", json={"username": "lan", "password": "S3cret-Pass"})  # no case: the same name
    assert taken.status_code == 409
    register(client)  # Alice
    with client.app.state.session_factory() as db, pytest.raises(NameTaken):
        create_virtual(db, "ALICE")


@pytest.mark.parametrize("password", ["", "!", "S3cret-Pass", "x" * 200])
def test_nobody_signs_in_as_a_virtual_person_with_any_password(client, password):
    make(client)
    response = client.post("/auth/login", json={"username": "Lan", "password": password})
    assert response.status_code in (401, 403, 422) and "sn_token" not in response.headers.get("set-cookie", "")


def test_no_session_and_no_token_is_ever_issued_for_one(client, monkeypatch):
    uid = make(client)
    with client.app.state.session_factory() as db:
        user = db.get(User, uid)
        with pytest.raises(HTTPException) as refused:
            begin_session(None, None, db, user, None, "password")  # (refused before it touches the request)
        assert refused.value.status_code == 403
        with pytest.raises(HTTPException) as again:
            issue_session(None, user, None, "sid")  # the refresh of a token that could not exist
        assert again.value.status_code == 403
        assert db.get(User, uid).token_version == 0


def test_a_virtual_person_is_never_a_match_for_a_face_or_a_voice(client):
    from api.center.identify import FACE, VOICE

    make(client)
    with client.app.state.session_factory() as db:
        for kind in (FACE, VOICE):
            rows = db.scalars(select(User).where(*kind.filters())).all()
            assert rows == []  # (it has no template either: the filter says it plainly)
    for kind in (FACE, VOICE):
        assert any("kind" in str(part) for part in kind.filters())

