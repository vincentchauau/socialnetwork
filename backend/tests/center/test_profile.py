from datetime import date, timedelta

from tests.center.helpers import CREDS, csrf, register

URL = "/auth/me/profile"


def put(client, session, body):
    return client.put(URL, json=body, headers=csrf(session))


def test_a_new_account_has_an_empty_profile(client):
    register(client)
    body = client.get(URL).json()
    assert body["name"] is None and body["address"] is None
    assert body["experience"] == [] and body["visibility"] == {}


def test_reading_needs_a_session_and_changing_needs_csrf(client):
    assert client.get(URL).status_code == 401
    session = register(client)
    assert client.put(URL, json={"name": "Ann"}).status_code == 403
    assert put(client, session, {"name": "Ann"}).status_code == 200


def test_the_fields_sent_are_saved_and_the_others_are_left_alone(client):
    session = register(client)
    first = {"name": "Nguyễn Văn An", "address": "12 Lê Lợi, Q1", "city": "TP.HCM"}
    assert put(client, session, first).status_code == 200
    again = put(client, session, {"headline": "Kỹ sư phần mềm"}).json()
    assert again["name"] == "Nguyễn Văn An" and again["city"] == "TP.HCM" and again["headline"] == "Kỹ sư phần mềm"
    assert client.get(URL).json()["name"] == "Nguyễn Văn An"


def test_null_or_an_empty_text_clears_a_field(client):
    session = register(client)
    put(client, session, {"name": "Ann", "address": "somewhere"})
    cleared = put(client, session, {"name": None, "address": "   "}).json()
    assert cleared["name"] is None and cleared["address"] is None


def test_the_profile_survives_signing_out_and_in_again(client):
    session = register(client)
    put(client, session, {"name": "Ann", "skills": [{"name": "Python", "level": "advanced", "years": 5}]})
    client.cookies.clear()
    client.post("/auth/login", json=CREDS)
    body = client.get(URL).json()
    assert body["name"] == "Ann" and body["skills"] == [{"name": "Python", "level": "advanced", "years": 5}]


def test_lists_are_replaced_as_a_whole_and_items_are_checked(client):
    session = register(client)
    job = {"company": "ACME", "title": "Engineer", "start": "2020-01", "end": None, "description": "Built things"}
    saved = put(client, session, {"experience": [job]}).json()["experience"]
    assert saved[0]["company"] == "ACME" and saved[0]["type"] == "full_time"
    assert put(client, session, {"experience": []}).json()["experience"] == []
    assert put(client, session, {"experience": [{"company": "", "title": "x"}]}).status_code == 422
    assert put(client, session, {"experience": [{**job, "start": "2020-13"}]}).status_code == 422
    assert put(client, session, {"experience": [{**job, "salary": 1}]}).status_code == 422  # unknown field


def test_a_list_has_a_size_limit(client):
    session = register(client)
    too_many = [{"name": f"skill {i}"} for i in range(51)]
    assert put(client, session, {"skills": too_many}).status_code == 422
    assert put(client, session, {"skills": too_many[:50]}).status_code == 200


def test_web_addresses_must_be_http_or_https(client):
    session = register(client)
    assert put(client, session, {"avatar_url": "javascript:alert(1)"}).status_code == 422
    assert put(client, session, {"avatar_url": "data:text/html,x"}).status_code == 422
    assert put(client, session, {"links": [{"kind": "github", "url": "ftp://x.org"}]}).status_code == 422
    ok = put(client, session, {"links": [{"kind": "github", "url": "https://github.com/ann"}]})
    assert ok.status_code == 200


def test_birth_date_rules(client):
    session = register(client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert put(client, session, {"birth_date": tomorrow}).status_code == 422
    assert put(client, session, {"birth_date": "1899-12-31"}).status_code == 422
    assert put(client, session, {"birth_date": "1990-05-17"}).json()["birth_date"] == "1990-05-17"
    for dropped in ("gender", "alias", "website", "desired_salary_min", "open_to_work"):
        assert put(client, session, {dropped: None}).status_code == 422  # no longer part of the profile


def test_visibility_names_known_parts_and_levels_only(client):
    session = register(client)
    assert put(client, session, {"visibility": {"address": "private", "experience": "public"}}).status_code == 200
    assert put(client, session, {"visibility": {"address": "everyone"}}).status_code == 422
    assert put(client, session, {"visibility": {"shoe_size": "public"}}).status_code == 422


def test_unknown_fields_are_refused(client):
    session = register(client)
    assert put(client, session, {"group": "admin"}).status_code == 422
    assert put(client, session, {"password_hash": "x"}).status_code == 422


def test_one_account_cannot_change_anothers_profile(client):
    session = register(client)
    put(client, session, {"name": "Alice"})
    client.cookies.clear()
    bob = register(client, {"username": "Bobby", "password": "S3cret-Pass"})
    assert client.get(URL).json()["name"] is None
    put(client, bob, {"name": "Bob"})
    client.cookies.clear()
    client.post("/auth/login", json=CREDS)
    assert client.get(URL).json()["name"] == "Alice"


def test_the_skills_of_a_profile_are_put_in_the_vocabulary_that_jobs_and_courses_share(client):
    from sn_shared.skills import Skill

    session = register(client)
    assert put(client, session, {"skills": [{"name": "Python", "level": "advanced"}, {"name": "SQL"}]}).status_code == 200
    with client.app.state.session_factory() as db:
        assert {(s.key, s.name) for s in db.query(Skill)} == {("python", "Python"), ("sql", "SQL")}
