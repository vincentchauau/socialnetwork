from tests.center.helpers import csrf, register

PROFILE = "/auth/me/profile"


def _owner(client, username, creds_extra=None):
    creds = {"username": username, "password": "Correct-Horse-9"}
    session = register(client, creds)
    client.put(PROFILE, json={"name": "Ann Le", "headline": "Engineer", "skills": [{"name": "Python"}]}, headers=csrf(session))
    return session


def _set_visibility(client, session, visibility):
    assert client.put(PROFILE, json={"visibility": visibility}, headers=csrf(session)).status_code == 200


def test_the_owner_reads_the_whole_cv_and_nothing_is_hidden(client):
    session = _owner(client, "annle")
    body = client.get("/auth/cv/annle").json()
    assert body["name"] == "Ann Le" and body["hidden"] == []
    assert body["skills"][0]["name"] == "Python"


def test_a_part_that_is_not_public_is_hidden_from_anyone_else(client):
    session = _owner(client, "annle")
    _set_visibility(client, session, {"headline": "public", "skills": "employers"})
    client.cookies.clear()
    body = client.get("/auth/cv/annle").json()
    assert body["headline"] == "Engineer"
    assert body["name"] is None and "name" in body["hidden"]
    assert body["skills"] == [] and "skills" in body["hidden"]


def test_a_signed_in_person_reads_the_employers_parts(client):
    session = _owner(client, "annle")
    _set_visibility(client, session, {"skills": "employers"})
    client.cookies.clear()
    register(client, {"username": "bobtran", "password": "Correct-Horse-9"})
    body = client.get("/auth/cv/annle").json()
    assert body["skills"][0]["name"] == "Python"


def test_an_unknown_person_is_not_found_and_the_visibility_is_not_shown(client):
    assert client.get("/auth/cv/nobody").status_code == 404
    _owner(client, "annle")
    body = client.get("/auth/cv/ANNLE").json()  # the name is not case sensitive
    assert body["visibility"] == {}
