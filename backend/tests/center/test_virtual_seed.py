"""The pool of virtual people is fixed, complete, and safe to seed again."""

from sqlalchemy import func, select

from api.center import cli
from api.center.handles import is_valid_username
from api.center.models import User
from api.center.virtual_seed import POOL_SIZE, candidate_names, seed_pool
from tests.center.helpers import register


def count(client):
    with client.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(User).where(User.kind == "virtual"))


def test_the_list_of_names_is_fixed_valid_and_without_repeats():
    names = candidate_names()
    assert names == candidate_names() and len(names) == POOL_SIZE
    assert len({n.lower() for n in names}) == POOL_SIZE and all(is_valid_username(n) for n in names)


def test_seeding_adds_the_whole_pool_once(client):
    with client.app.state.session_factory() as db:
        assert seed_pool(db) == POOL_SIZE
        db.commit()
        assert seed_pool(db) == 0
    assert count(client) == POOL_SIZE


def test_a_name_taken_by_a_person_is_skipped_not_stolen(client):
    first = candidate_names()[0]
    client.post("/auth/register", json={"username": first.lower(), "password": "S3cret-Pass"})
    with client.app.state.session_factory() as db:
        assert seed_pool(db) == POOL_SIZE - 1
        db.commit()
    with client.app.state.session_factory() as db:
        assert db.scalar(select(User.kind).where(User.username == first.lower())) == "human"


def test_the_command_seeds_and_repeats_harmlessly(client, capsys):
    open_session = client.app.state.session_factory
    assert cli.main(["seed-virtual"], open_session=open_session) == 0
    assert cli.main(["seed-virtual"], open_session=open_session) == 0
    assert "Added 0" in capsys.readouterr().out and count(client) == POOL_SIZE
    register(client)


def test_each_name_has_the_same_adult_profile_every_time():
    from datetime import date

    from api.center.virtual_profiles import profile_for

    name = candidate_names()[0]
    first = profile_for(name)
    assert first == profile_for(name) and first != profile_for(candidate_names()[1])
    assert len(first["interests"]) == 3 and first["persona_role"] and first["speaking_style"]
    assert (date.today() - first["birth_date"]).days > 18 * 365


def test_the_seeded_people_carry_their_profile_and_announce_its_public_part(client):
    import json

    from api.center.models import AccountEvent

    with client.app.state.session_factory() as db:
        seed_pool(db, 3)
        db.commit()
        person = db.scalar(select(User).where(User.kind == "virtual").order_by(User.id))
        assert person.city and person.birth_date and person.persona_role and person.interests
        event = db.scalar(select(AccountEvent).where(AccountEvent.user_id == person.id))
        body = json.loads(event.payload)
        assert body["interests"] == person.interests and body["birth_year"] == person.birth_date.year
        assert body["persona_role"] == person.persona_role and body["speaking_style"] == person.speaking_style  # the agent needs the script
