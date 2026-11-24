"""More rows for the pages that look empty: extra products with orders and reviews, extra jobs with applications, learners, and the private data of the real people."""

import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.chat.models import Message, Room, RoomMember
from api.face.models import Measurement
from api.job.models import JobApplicant, JobDescription
from api.market.constants import STATUS_CANCELLED, STATUS_DELIVERED, STATUS_PAID, STATUS_SHIPPED
from api.market.models import CartItem, Order, Product, seller_ids_text
from api.market.payments import REFERENCE_PREFIX
from sn_shared import skills as shared_skills
from sn_shared.comments import Comment

from tools.seed_cast import keys_of
from tools.seed_demo_data.jobs import COVER_LETTERS, EMPLOYER_NOTES, VI, EN
from tools.seed_demo_data.more import DIALOGUES, JOBS, PRODUCTS, REVIEW_TEXTS
from tools.seed_env import Env
from tools.seed_jobs import PATHS, _history, _resume

SELLERS = 8
ORDERS = 26
STATUS_MIX = (STATUS_DELIVERED,) * 9 + (STATUS_SHIPPED,) * 3 + (STATUS_PAID,) * 3 + (STATUS_CANCELLED,) * 2
EXTRA_LEARNERS = 40


def seed_more_market(env: Env, db: Session) -> str | None:
    if db.scalar(select(func.count()).select_from(Product).where(Product.name == PRODUCTS[0][0])):
        return "the extra products are already there"
    humans = list(env.cast.humans)
    sellers = []
    for _ in range(SELLERS):
        sellers.append(env.cast.take(exclude={s.id for s in sellers}))
    products: list[Product] = []
    for index, (name, description, price, stock, category) in enumerate(PRODUCTS):
        seller = humans[0] if humans and index % 8 == 0 else sellers[index % len(sellers)]
        image = None
        product = Product(
            seller_id=seller.id, name=name, description=description, price_cents=price, stock=stock, image_url=image, category=category,
            is_active=True, created_at=env.ago(env.rng.uniform(2, 58)),
        )
        db.add(product)
        products.append(product)
    db.flush()
    buyers = [*humans, *[env.cast.take() for _ in range(12)]]
    bought: dict[tuple[int, int], Order] = {}
    for number in range(ORDERS):
        buyer = humans[0] if humans and number % 5 == 0 else buyers[number % len(buyers)]
        picked = env.rng.sample(products, env.rng.randint(1, 3))
        if any(p.seller_id == buyer.id for p in picked):
            picked = [p for p in picked if p.seller_id != buyer.id] or [next(p for p in products if p.seller_id != buyer.id)]
        lines = [(p, env.rng.randint(1, 3)) for p in picked]
        status = env.rng.choice(STATUS_MIX)
        items = [{"product_id": p.id, "seller_id": p.seller_id, "name": p.name, "unit_price_cents": p.price_cents, "quantity": q} for p, q in lines]
        order = Order(
            buyer_id=buyer.id, status=status, total_cents=sum(i["unit_price_cents"] * i["quantity"] for i in items),
            payment_reference=REFERENCE_PREFIX + secrets.token_hex(12), items=items, seller_ids=seller_ids_text(items),
            created_at=env.ago(env.rng.uniform(1, 55)),
        )
        db.add(order)
        if status != STATUS_CANCELLED:
            for p, q in lines:
                p.stock = max(0, p.stock - q)
        if status == STATUS_DELIVERED:
            for p, _ in lines:
                bought.setdefault((buyer.id, p.id), order)
    for number, ((buyer_id, product_id), order) in enumerate(bought.items()):
        if number % 3 == 2:
            continue  # not everybody writes a review
        rating = env.rng.choices((5, 4, 3), weights=(6, 3, 1))[0]
        texts = REVIEW_TEXTS[rating]
        written = min(order.created_at.replace(tzinfo=env.now.tzinfo) + timedelta(days=env.rng.randint(4, 9)), env.now - timedelta(hours=1))
        db.add(Comment(object_type="product", object_id=product_id, user_id=buyer_id, content=texts[number % len(texts)], rating=rating, once=True, created_at=written))
    for human in humans[:1]:  # something in the cart of the real person
        for product in [p for p in products if p.seller_id != human.id][1:3]:
            db.add(CartItem(user_id=human.id, product_id=product.id, quantity=1))
    return None


def seed_more_jobs(env: Env, db: Session) -> str | None:
    if db.scalar(select(func.count()).select_from(JobDescription).where(JobDescription.company == JOBS[0][1])):
        return "the extra jobs are already there"
    humans = list(env.cast.humans)
    shared_skills.register(db, sorted({name for job in JOBS for name in (*job[8], *job[9])}))
    jobs: list[JobDescription] = []
    for index, (title, company, department, location, remote, kind, seniority, years, required, preferred, salary, description) in enumerate(JOBS):
        owner = humans[0] if humans and index % 6 == 0 else env.cast.take(keys_of(required + preferred))
        low, high, currency, period = salary
        job = JobDescription(
            owner_id=owner.id, title=title, company=company, department=department, location=location, remote=remote, employment_type=kind,
            seniority=seniority, openings=1 + index % 3, experience_min_years=years, education_min="bachelor" if years else "high_school",
            skills_required=[{"name": n, "level": "intermediate", "years": years or None} for n in required],
            skills_preferred=[{"name": n, "level": "beginner", "years": None} for n in preferred], languages=[VI, EN] if index % 2 == 0 else [VI],
            responsibilities=[f"Tham gia các công việc chính của {department.lower()}", "Phối hợp với các nhóm khác để hoàn thành mục tiêu quý", "Báo cáo tiến độ hằng tuần"],
            benefits=["Bảo hiểm sức khỏe", "Thưởng theo hiệu quả", "Môi trường học hỏi, đào tạo nội bộ"],
            salary_min=low, salary_max=high, currency=currency, salary_period=period, description=description, status="open",
            expires_at=env.now + timedelta(days=20 + 5 * index), created_at=env.ago(env.rng.uniform(2, 50)),
        )
        db.add(job)
        db.flush()
        shared_skills.register(db, [*required, *preferred])
        job.skill_keys = shared_skills.keys_of([*required, *preferred])
        jobs.append(job)
    applicants = [*humans, *[env.cast.take() for _ in range(14)]]
    states = list(PATHS)
    seen: set[tuple[int, int]] = set()
    for number in range(38):
        job = jobs[number % len(jobs)]
        person = humans[0] if humans and number % 9 == 0 else applicants[number % len(applicants)]
        if person.id == job.owner_id or (job.id, person.id) in seen:
            continue
        seen.add((job.id, person.id))
        state = states[number % len(states)]
        skills = ", ".join(i["name"] for i in job.skills_required[:2])
        db.add(JobApplicant(
            job_description_id=job.id, user_id=person.id, saved=number % 4 == 0, status=state,
            cover_letter=COVER_LETTERS[number % len(COVER_LETTERS)].format(company=job.company, title=job.title, skills=skills),
            resume=_resume(person, job), contact_email=f"{person.username.lower()}@example.com",
            employer_note=EMPLOYER_NOTES[number % len(EMPLOYER_NOTES)] if state != "submitted" else "",
            history=_history(env, state, env.rng.uniform(3, 30)),
        ))
    for human in humans[:1]:  # jobs the real person saved without applying
        for job in jobs[1:6:2]:
            if (job.id, human.id) not in seen and job.owner_id != human.id:
                db.add(JobApplicant(job_description_id=job.id, user_id=human.id, saved=True, status=None, cover_letter="", resume=None, history=[]))
    return None


def seed_more_face(env: Env, db: Session) -> str | None:
    """Face measurements of the real person, rising over some weeks."""
    humans = list(env.cast.humans)
    if not humans:
        return "there is no real person yet"
    human = humans[0]
    if db.scalar(select(func.count()).select_from(Measurement).where(Measurement.user_id == human.id)):
        return "the real person already has measurements"
    age = 40.0
    for symmetry in (71, 74, 73, 78, 80, 82):
        db.add(Measurement(
            user_id=human.id, created_at=env.ago(age), symmetry=symmetry, eye=symmetry - 3, nose=symmetry + 2, mouth=symmetry - 1, ear=symmetry + 1,
            angle=round(env.rng.uniform(-3, 3), 1), note="Đo buổi sáng, ánh sáng cửa sổ" if symmetry % 2 else "Đo buổi tối, ánh sáng đèn bàn",
        ))
        age -= 6
    return None


def seed_more_dms(env: Env, db: Session) -> str | None:
    """Private conversations between the real person and some of the virtual ones."""
    humans = list(env.cast.humans)
    if not humans:
        return "there is no real person to talk to"
    human = humans[0]
    if db.scalar(select(func.count()).select_from(Room).where(Room.kind == "dm", Room.user_id == human.id)):
        return "the private conversations are already there"
    friends: list = []
    for number, dialogue in enumerate(DIALOGUES):
        friend = env.cast.take(exclude={f.id for f in friends} | {human.id})
        friends.append(friend)
        low, high = sorted((human.id, friend.id))
        began = env.ago(env.rng.uniform(3, 30))
        room = Room(slug=f"dm-{low}-{high}", kind="dm", title=f"{human.username} & {friend.username}"[:80], user_id=human.id,
                    visibility="private", join_policy="invite", state="open", capacity=2)
        db.add(room)
        db.flush()
        for person in (human, friend):
            db.add(RoomMember(room_id=room.id, user_id=person.id, status="joined"))
        moment = began
        for first, second in dialogue:
            for speaker, text in ((human if number % 2 == 0 else friend, first), (friend if number % 2 == 0 else human, second)):
                moment += timedelta(minutes=env.rng.randint(1, 9))
                db.add(Message(room_id=room.id, user_id=speaker.id, content=text, created_at=moment))
    return None
