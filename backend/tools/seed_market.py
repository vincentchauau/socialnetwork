"""Products, carts, orders and the reviews of delivered purchases."""

import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.market.constants import STATUS_CANCELLED, STATUS_DELIVERED
from api.market.models import CartItem, Order, Product, seller_ids_text
from api.market.payments import REFERENCE_PREFIX
from sn_shared.comments import Comment

from tools.seed_cast import PersonInfo
from tools.seed_demo_data.market import ADMIN, CART, ORDERS, PRODUCTS, REVIEWS
from tools.seed_env import Env

SELLER_SLOTS = 5
BUYER_SLOTS = 5


def slot_people(env: Env, count: int, exclude: set[int]) -> list[PersonInfo]:
    people: list[PersonInfo] = []
    for _ in range(count):
        people.append(env.cast.take(exclude=exclude | {p.id for p in people}))
    return people


def seed_market(env: Env, db: Session) -> str | None:
    names = [row[0] for row in PRODUCTS]
    if db.scalar(select(func.count()).select_from(Product).where(Product.name.in_(names))):
        return "the demo products are already there"
    sellers = slot_people(env, SELLER_SLOTS, set())
    buyers = slot_people(env, BUYER_SLOTS, {p.id for p in sellers})
    admin = env.cast.admin

    def person(slot, pool: list[PersonInfo]) -> PersonInfo:
        return (admin or pool[0]) if slot == ADMIN else pool[slot]

    products: list[Product] = []
    for index, (name, description, price, stock, category, slot) in enumerate(PRODUCTS):
        image = None
        product = Product(
            seller_id=person(slot, sellers).id, name=name, description=description, price_cents=price, stock=stock,
            image_url=image, category=category, is_active=True, created_at=env.ago(58 - index // 5),
        )
        db.add(product)
        products.append(product)
    db.flush()
    sold: dict[int, int] = {}
    delivered: dict[int, tuple[int, Order]] = {}  # product index -> (buyer, order)
    for slot, lines, status, age in ORDERS:
        buyer = person(slot, buyers)
        items = [
            {"product_id": products[p].id, "seller_id": products[p].seller_id, "name": products[p].name,
             "unit_price_cents": products[p].price_cents, "quantity": qty}
            for p, qty in lines
        ]
        if any(item["seller_id"] == buyer.id for item in items):  # nobody buys their own product
            buyer = next(b for b in buyers if all(item["seller_id"] != b.id for item in items))
        order = Order(
            buyer_id=buyer.id, status=status, total_cents=sum(i["unit_price_cents"] * i["quantity"] for i in items),
            payment_reference=REFERENCE_PREFIX + secrets.token_hex(12), items=items, seller_ids=seller_ids_text(items),
            created_at=env.ago(age),
        )
        db.add(order)
        if status != STATUS_CANCELLED:  # a cancelled order gave its stock back
            for p, qty in lines:
                sold[p] = sold.get(p, 0) + qty
        if status == STATUS_DELIVERED:
            for p, _ in lines:
                delivered[p] = (buyer.id, order)
    for index, quantity in sold.items():
        products[index].stock -= quantity
    for slot, p, qty in CART:
        buyer = person(slot, buyers)
        if buyer.id == products[p].seller_id:
            continue
        db.add(CartItem(user_id=buyer.id, product_id=products[p].id, quantity=qty))
    db.flush()
    for p, (rating, text) in REVIEWS.items():
        buyer_id, order = delivered[p]
        written = order.created_at.replace(tzinfo=env.now.tzinfo) + timedelta(days=env.rng.randint(5, 9))
        db.add(Comment(
            object_type="product", object_id=products[p].id, user_id=buyer_id, content=text, rating=rating, once=True,
            created_at=min(written, env.now - timedelta(hours=1)),
        ))
    return None
