import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from sn_shared import COOKIE_NAME, create_token, skills
from sn_shared.db import make_engine
from sn_shared.testing import install_test_keys

install_test_keys()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    skills.ensure_tables(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


def test_the_many_ways_to_write_a_skill_are_one_key():
    assert skills.skill_key("  Python ") == "python"
    assert skills.skill_key("NodeJS") == skills.skill_key("node.js") == skills.skill_key("Node") == "node.js"
    assert skills.skill_key("Lập  Trình") == "lap trinh" and skills.skill_key("Đồng bộ") == "dong bo"
    assert skills.skill_key("C Sharp") == skills.skill_key("C#") == "c#"
    assert skills.skill_key("   ") == "" and len(skills.skill_key("x" * 200)) == 60


def test_a_skill_is_put_in_the_catalog_once(db):
    assert skills.register(db, ["Python", "python", "Node.js", " "]) == ["python", "node.js"]
    skills.register(db, ["PYTHON"])
    db.commit()
    assert {(s.key, s.name) for s in db.query(skills.Skill)} == {("python", "Python"), ("node.js", "Node.js")}


def test_suggestions_start_like_the_words_and_come_in_order_of_key(db):
    skills.register(db, ["PostgreSQL", "Python", "Photoshop", "Go"])
    db.commit()
    assert [s.name for s in skills.suggest(db, "p")] == ["Photoshop", "PostgreSQL", "Python"]
    assert [s.name for s in skills.suggest(db, "POSTGRES")] == ["PostgreSQL"]  # an alias of the key
    assert [s.name for s in skills.suggest(db, "", 2)] == ["Go", "Photoshop"]
    assert skills.suggest(db, "100%") == []


def test_keys_of_names_are_once_each_and_sorted():
    assert skills.keys_of(["Python", "python", "Node.js", " ", "NodeJS"]) == ["node.js", "python"]


def test_a_job_that_asks_for_nothing_has_no_score():
    assert skills.match([], [], [{"name": "Python"}]).score is None


def test_what_a_person_has_against_what_is_asked():
    result = skills.match(
        [{"name": "Python", "level": "advanced", "years": 3}, {"name": "SQL"}, {"name": "Docker"}],
        [{"name": "Kubernetes"}],
        [{"name": "python", "level": "expert", "years": 5}, {"name": "sql", "level": "beginner"}, {"name": "K8s"}],
    )
    assert result.matched == ["Python", "SQL"] and result.missing == ["Docker"] and result.partial == []
    assert result.missing_preferred == []  # k8s is kubernetes
    assert result.score == round((0.8 * (2 / 3) + 0.2 * 1) * 100)


def test_a_skill_below_the_level_or_the_years_asked_counts_for_half():
    result = skills.match(
        [{"name": "Python", "level": "expert"}, {"name": "Go", "years": 5}, {"name": "Rust", "years": 2}],
        [],
        [{"name": "Python", "level": "intermediate"}, {"name": "Go", "years": 1}, {"name": "Rust"}],
    )
    assert result.partial == ["Python", "Go"] and result.matched == ["Rust"]  # no years told: not held against them
    assert result.score == round((0.5 + 0.5 + 1) / 3 * 100)


def test_only_liked_skills_make_the_score_and_nothing_in_common_is_zero():
    assert skills.match([], [{"name": "A"}, {"name": "B"}], [{"name": "a"}]).score == 50
    assert skills.match([{"name": "A"}], [], []).score == 0 and skills.match([{"name": "A"}], [], []).missing == ["A"]


def test_the_suggestions_over_http_need_sign_in():
    engine = make_engine("sqlite://")
    skills.ensure_tables(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(skills.skills_router())
    with app.state.session_factory() as session:
        skills.register(session, ["Python", "Pandas", "Go"])
        session.commit()
    with TestClient(app) as client:
        assert client.get("/skills").status_code == 401
        headers = {"Cookie": f"{COOKIE_NAME}={create_token(1, 'alice')}"}
        assert [s["name"] for s in client.get("/skills", params={"q": "p"}, headers=headers).json()] == ["Pandas", "Python"]
        assert client.get("/skills", params={"limit": 0}, headers=headers).status_code == 422
