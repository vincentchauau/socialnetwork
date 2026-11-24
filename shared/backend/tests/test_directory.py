from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from sn_shared.db import make_engine
from sn_shared.directory import Person, ensure_table_for_sqlite
from sn_shared.testing import add_person


@pytest.fixture
def factory():
    engine = make_engine("sqlite://")
    ensure_table_for_sqlite(engine)
    return sessionmaker(engine, expire_on_commit=False)


def read(factory, user_id):
    with factory() as db:
        return db.get(Person, user_id)


def test_a_human_shows_only_what_the_profile_makes_public(factory):
    add_person(factory, 1, "alice", name="Alice Nguyen", headline="Gardener", region="Huế", avatar_url="https://x.test/a.png",
               summary="I grow roses", visibility={"headline": "public", "location": "public", "name": "employers"})
    view = read(factory, 1).view()
    assert view.headline == "Gardener" and view.region == "Huế"
    assert view.display_name == "" and view.avatar == ""  # not public: not shown
    assert view.summary_public is False and view.summary == "I grow roses"  # written; read only by friends (the caller decides)
    own = read(factory, 1).view(own=True)
    assert own.display_name == "Alice Nguyen" and own.avatar == "https://x.test/a.png"


def test_a_human_with_no_visibility_shows_nothing_but_the_username(factory):
    add_person(factory, 1, "alice", name="Alice", headline="Gardener", city="Huế", visibility=None)
    view = read(factory, 1).view()
    assert (view.display_name, view.headline, view.region, view.avatar) == ("", "", "", "")
    assert read(factory, 1).username == "alice"


def test_a_virtual_person_shows_all_of_it_with_the_age_and_interests(factory):
    add_person(factory, 500, "Lan_Nguyen", kind="virtual", name="Lan Nguyen", headline="Bạn trò chuyện", region="Miền Bắc", city="Hà Nội",
               birth_date=date(1990, 5, 1), interests=["yoga", "cà phê"], summary="Xin chào", persona_role="gia sư", speaking_style="nhẹ nhàng")
    person = read(factory, 500)
    view = person.view()
    assert (view.display_name, view.region, view.birth_year, view.interests, view.summary_public) == ("Lan Nguyen", "Miền Bắc", 1990, ["yoga", "cà phê"], True)
    assert person.is_virtual and person.persona_role == "gia sư" and person.speaking_style == "nhẹ nhàng"


def test_a_virtual_person_without_a_name_is_shown_by_their_username(factory):
    add_person(factory, 500, "Lan_Nguyen", kind="virtual")
    assert read(factory, 500).view().display_name == "Lan Nguyen"


def test_a_human_has_no_age_and_no_interests_for_others(factory):
    add_person(factory, 1, "alice", birth_date=date(1990, 5, 1), interests=["yoga"], visibility={"summary": "public"})
    view = read(factory, 1).view()
    assert view.birth_year is None and view.interests == [] and view.summary_public is True


def test_the_place_is_the_region_or_else_the_city_and_the_summary_is_cut(factory):
    add_person(factory, 1, "a", city="Huế", summary="x" * 900, visibility={"location": "public"})
    add_person(factory, 2, "b", region="Miền Trung", city="Huế")
    assert read(factory, 1).place == "Huế" and read(factory, 2).place == "Miền Trung"
    assert len(read(factory, 1).view().summary) == 500


def test_adding_a_person_again_changes_the_row(factory):
    add_person(factory, 1, "alice")
    add_person(factory, 1, "alicia", headline="New")
    assert read(factory, 1).username == "alicia" and read(factory, 1).headline == "New"


def test_names_reads_each_username_once_and_names_nobody_for_gone_people(factory):
    from sn_shared.directory import DELETED_USERNAME, names

    add_person(factory, 1, "alice")
    with factory() as db:
        assert names(db, (user_id for user_id in [1, 0, -5, 99])) == {1: "alice", 0: DELETED_USERNAME, -5: DELETED_USERNAME, 99: DELETED_USERNAME}
