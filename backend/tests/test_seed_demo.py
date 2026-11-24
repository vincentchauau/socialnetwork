"""The demo seeder: counts, who owns what, consistency between tables, idempotency and what the modules' own readers say."""

import json
import re
from collections import Counter

import pytest
from sqlalchemy import String, func, select, text
from sqlalchemy.orm import Session

from sn_shared import comments as shared_comments
from sn_shared import skills as shared_skills
from sn_shared.db import make_engine
from sn_shared.directory import Person, ensure_table_for_sqlite
from sn_shared.security import TokenPayload
from sn_shared.skills import Skill, skill_key
from api.chat.social.models import Edge, Notification, Report
from api.chat.social.models import Base as SocialBase

import api.chat.models as chat_models
import api.face.models as face_models
import api.job.models as job_models
import api.market.models as market_models
from api.chat.db import Base as ChatBase
from api.face.db import Base as FaceBase
from api.job.applicants import APPLICATION_FLOW
from api.job.serializers import application_out, applicant_out, detail, summaries
from api.market.constants import ORDER_FLOW
from api.market.db import Base as MarketBase
from api.market.models import seller_ids_text
from tools import seed_demo

# The first set of demo data; the groups added since (more of everything, the gallery, chat, games...) have tests of their own.
BASE_GROUPS = frozenset({"jobs", "market", "face", "social"})
EXPECTED = {
    "skills": 25, "job_descriptions": 10, "job_applicants": 20, "products": 15, "cart_items": 6,
    "orders": 8, "measurements": 10, "notifications": 12, "reports": 4,
}
PEOPLE_SKILLS = [["Python", "SQL"], ["Python"], ["React", "JavaScript"], ["Docker", "Linux"], ["Excel"], ["Giao tiếp", "Thuyết trình"], ["Scrum"], ["Marketing số", "SEO"], []]
LOREM = re.compile(r"lorem|ipsum|\btest\b", re.I)
BASES = (MarketBase, FaceBase, ChatBase, SocialBase)


@pytest.fixture
def url(tmp_path):
    address = f"sqlite:///{tmp_path / 'app.db'}"
    engine = make_engine(address)
    for base in (*BASES, job_models.Base):
        base.metadata.create_all(engine)
    shared_skills.ensure_tables(engine)
    shared_comments.ensure_table(engine)
    ensure_table_for_sqlite(engine)
    with Session(engine) as db:
        db.add(Person(user_id=-1, username="system", kind="system"))
        db.add(Person(user_id=1, username="User@123", kind="human"))
        for number in range(2, 42):
            names = PEOPLE_SKILLS[number % len(PEOPLE_SKILLS)]
            db.add(Person(
                user_id=number, username=f"Binh_Phan{number}", kind="virtual", headline="Lập trình viên", summary="Mình thích làm việc nhóm.",
                skills=[{"name": n, "level": "intermediate", "years": 2} for n in names],
            ))
        db.add(chat_models.Room(slug="phong-cafe", title="Phòng cà phê", user_id=3))
        db.flush()
        db.add(chat_models.Message(room_id=1, user_id=3, content="Chào mọi người"))
        db.commit()
    engine.dispose()
    return address


@pytest.fixture
def seeded(url):
    result = seed_demo.seed(url, embedder="dummy", only=BASE_GROUPS)
    engine = make_engine(url)
    yield result, engine
    engine.dispose()


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_second_run_adds_nothing(url):
    seed_demo.seed(url, embedder="dummy", only=BASE_GROUPS)
    again = seed_demo.seed(url, embedder="dummy", only=BASE_GROUPS)
    assert not any(again.counts.values())
    assert len(again.skipped) == len(BASE_GROUPS)


def test_jobs_and_applications_are_coherent(seeded):
    _, engine = seeded
    with Session(engine) as db:
        jobs = {j.id: j for j in db.scalars(select(job_models.JobDescription))}
        catalog = {s.key for s in db.scalars(select(Skill))}
        for job in jobs.values():
            assert job.status == "open" and job.salary_min <= job.salary_max and job.currency in ("VND", "USD")
            assert {skill_key(i["name"]) for i in job.skills_required + job.skills_preferred} <= catalog
        assert sum(len(job.skills_required) for job in jobs.values()) >= 20 and sum(len(job.skills_preferred) for job in jobs.values()) >= 20
        assert all(job.skill_keys == sorted({skill_key(i["name"]) for i in job.skills_required + job.skills_preferred}) for job in jobs.values())
        applied = saved_only = 0
        for row in db.scalars(select(job_models.JobApplicant)):
            job = jobs[row.job_description_id]
            assert row.user_id != job.owner_id
            if row.status is None:
                saved_only += 1
                assert row.saved and not row.history
                continue
            applied += 1
            steps = [h["status"] for h in row.history]
            assert steps[0] == "submitted" and steps[-1] == row.status and row.resume["skills"]
            assert all(APPLICATION_FLOW.allows(a, b) for a, b in zip(steps, steps[1:]))
            assert application_out(row, job).history and applicant_out(row, job, "x").match is not None
        assert (applied, saved_only) == (16, 4)
        assert {r.status for r in db.scalars(select(job_models.JobApplicant))} >= {"submitted", "interview", "offer", "rejected", None}
        viewer = TokenPayload(user_id=1, username="User@123", expires_at=0)
        assert len(summaries(db, viewer, list(jobs.values()))) == 10
        shown = detail(db, viewer, next(j for j in jobs.values() if j.owner_id != 1))
        assert shown.skills_required and shown.match is not None


def test_market_totals_stock_and_reviews(seeded):
    _, engine = seeded
    with Session(engine) as db:
        products = {p.id: p for p in db.scalars(select(market_models.Product))}
        statuses = set()
        for order in db.scalars(select(market_models.Order)):
            statuses.add(order.status)
            assert order.total_cents == sum(i["unit_price_cents"] * i["quantity"] for i in order.items)
            assert order.seller_ids == seller_ids_text(order.items)
            assert all(i["seller_id"] == products[i["product_id"]].seller_id != order.buyer_id for i in order.items)
            assert order.payment_reference.startswith("fake_") == (order.status != "pending_payment")
            assert order.status in ORDER_FLOW.states
        assert statuses == {"paid", "shipped", "delivered", "cancelled"}
        assert all(p.stock >= 0 and p.price_cents > 0 and p.image_url is None for p in products.values())
        bought = {(o.buyer_id, i["product_id"]) for o in db.scalars(select(market_models.Order).where(market_models.Order.status == "delivered")) for i in o.items}
        reviews = list(db.scalars(select(shared_comments.Comment).where(shared_comments.Comment.object_type == "product")))
        assert len(reviews) == 8 and all((r.user_id, r.object_id) in bought and 1 <= r.rating <= 5 and r.once for r in reviews)
        for item in db.scalars(select(market_models.CartItem)):
            assert products[item.product_id].seller_id != item.user_id and 1 <= item.quantity <= products[item.product_id].stock


def test_social_rows_agree_with_each_other(seeded):
    _, engine = seeded
    with Session(engine) as db:
        edges = {(e.src_id, e.dst_id): e for e in db.scalars(select(Edge).where(Edge.kind == "friend"))}
        for note in db.scalars(select(Notification)):
            if note.kind == "friend_request":
                assert (note.actor_id, note.user_id) in edges
            else:
                assert note.kind == "friend_accepted" and edges[(note.user_id, note.actor_id)].status == "accepted"
            assert note.payload["user_id"] == note.actor_id
        assert Counter(e.status for e in edges.values()) == {"accepted": 4, "pending": 4}
        assert {r.reason for r in db.scalars(select(Report))} <= set(("spam", "abuse", "impersonation", "illegal", "other"))
        assert {r.target_type for r in db.scalars(select(Report))} >= {"user", "message", "room"}
        ids = set(db.scalars(select(Person.user_id)))
        for report in db.scalars(select(Report).where(Report.target_type == "user")):
            assert int(report.target_id) in ids and int(report.target_id) != report.reporter_id


def test_other_tables(seeded):
    _, engine = seeded
    with Session(engine) as db:
        for row in db.scalars(select(face_models.Measurement)):
            assert all(0 <= v <= 100 for v in (row.symmetry, row.eye, row.nose, row.mouth, row.ear)) and 0 <= row.angle <= 90


