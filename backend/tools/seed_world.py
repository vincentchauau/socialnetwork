"""The pictures of the gallery folders, chat rooms with their talk, finished Werewolf games, roulette and meetings."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.chat.models import Meeting, Message, Room, RoomMember
from api.roulette.game import payout
from api.roulette.models import START_CHIPS, Spin, Wallet
from api.werewolf.models import FINISHED, Game, ids_text

from tools.seed_demo_data.world import GAMES, ROOMS
from tools.seed_env import Env

GALLERY_DEFAULT = "/data/Galleries"
PICTURE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
PHOTO_AGE_DAYS = 200  # the pictures are spread over this many days, so the gallery shows several months
HUMAN_SHARE = 12  # one picture in this many belongs to a real person (so their own page is not empty)
MEMBERS_PER_ROOM = 6
SPINS_PER_PLAYER = 12
PLAYERS = 14


def seed_chat(env: Env, db: Session) -> str | None:
    """Rooms of the chat with their members and a conversation in each."""
    if db.scalar(select(func.count()).select_from(Room).where(Room.slug.in_([room[0] for room in ROOMS]))):
        return "the demo rooms are already there"
    humans = list(env.cast.humans)
    for number, (slug, title, _description, category, _region, talk) in enumerate(ROOMS):
        owner = humans[number % len(humans)] if humans and number % 3 == 0 else env.cast.take()
        members = [owner]
        while len(members) < MEMBERS_PER_ROOM:
            members.append(env.cast.take(exclude={m.id for m in members}))
        for human in humans:
            if human.id not in {m.id for m in members} and number % 2 == 0:
                members.append(human)
        began = env.ago(40 - number * 4)
        room = Room(
            slug=slug, kind="chat", title=title, category=category, user_id=owner.id, visibility="public", join_policy="open", state="open",
        )
        db.add(room)
        db.flush()
        for person in members:
            db.add(RoomMember(room_id=room.id, user_id=person.id, status="joined"))
        last = began
        for who, minutes, text in talk:
            author = members[who % len(members)]
            last = began + timedelta(minutes=minutes + 1)
            db.add(Message(room_id=room.id, user_id=author.id, content=text, created_at=last))
    return None


def seed_games(env: Env, db: Session) -> str | None:
    """Finished games of the Werewolf, with the role and the fate of every player."""
    if db.scalar(select(func.count()).select_from(Game).where(Game.room_code.in_([game[0] for game in GAMES]))):
        return "the demo games are already there"
    for code, winner, days, roles, ago in GAMES:
        players = []
        taken: set[int] = set()
        for role, outcome, survived, lived in roles:
            person = env.cast.take(exclude=taken)
            taken.add(person.id)
            players.append({"user_id": person.id, "role": role, "outcome": outcome, "survived": survived, "days_survived": lived})
        human = next(iter(env.cast.humans), None)
        if human is not None and human.id not in taken and ago % 2 == 1:
            players[-1]["user_id"] = human.id  # the real person played in some games
        db.add(Game(
            room_code=code, status=FINISHED, winner=winner, days=days, size=len(players), finished_at=env.ago(ago), players=players,
            player_ids=ids_text(player["user_id"] for player in players),
        ))
    return None


def seed_roulette(env: Env, db: Session) -> str | None:
    """Wallets of some people and the spins that led to their chips."""
    if db.scalar(select(func.count()).select_from(Wallet)):
        return "there are wallets already"
    people = [*env.cast.humans, *[env.cast.take() for _ in range(PLAYERS)]]
    for person in people:
        balance = START_CHIPS
        age = 30.0
        for _ in range(SPINS_PER_PLAYER):
            number = env.rng.randint(0, 36)
            bets = []
            for _bet in range(env.rng.randint(1, 3)):
                kind = env.rng.choice(("red", "black", "odd", "even", "low", "high", "straight", "dozen"))
                pick = env.rng.randint(0, 36) if kind == "straight" else env.rng.randint(1, 3) if kind == "dozen" else None
                bets.append({"kind": kind, "pick": pick, "amount": env.rng.choice((5, 10, 20, 50))})
            for bet in bets:
                bet["payout"] = payout(bet["kind"], bet["pick"], bet["amount"], number)
            stake = sum(bet["amount"] for bet in bets)
            won = sum(bet["payout"] for bet in bets)
            balance = max(0, balance - stake + won)
            db.add(Spin(user_id=person.id, number=number, bets=bets, stake=stake, payout=won, balance_after=balance, created_at=env.ago(age)))
            age = max(age - env.rng.uniform(0.5, 3), 0.1)
        db.add(Wallet(user_id=person.id, chips=balance))
    return None


def seed_meetings(env: Env, db: Session) -> str | None:
    """A few video meetings of the demo rooms (all ended)."""
    if db.scalar(select(func.count()).select_from(Meeting)):
        return "there are meetings already"
    rooms = list(db.execute(select(Room.id, Room.slug, Room.user_id).where(Room.slug.in_([room[0] for room in ROOMS])).order_by(Room.id)))
    if not rooms:
        return "there are no demo rooms to meet in"
    for number, (room_id, slug, owner_id) in enumerate(rooms):
        for sitting in range(1 + number % 2):
            began = env.ago(20 - number * 2 - sitting * 6)
            db.add(Meeting(room_id=room_id, room_name=f"sn-{slug}-{sitting + 1}", started_by=owner_id, started_at=began, ended_at=began + timedelta(minutes=env.rng.randint(15, 75))))
    return None

