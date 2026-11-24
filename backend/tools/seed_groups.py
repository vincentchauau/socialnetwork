"""The groups of the seeder: (name, module whose database it writes, function), and the tables each one may add rows to."""

from api.face.models import Measurement
from api.job.models import JobApplicant, JobDescription
from api.chat.models import Meeting, Message, Room, RoomMember
from api.market.models import CartItem, Order, Product
from api.roulette.models import Spin, Wallet
from api.werewolf.models import Game
from sn_shared.comments import Comment
from sn_shared.skills import Skill
from api.chat.social.models import Edge, Notification, Report

from tools.seed_jobs import seed_jobs
from tools.seed_market import seed_market
from tools.seed_other import seed_face, seed_friends
from tools.seed_more import seed_more_dms, seed_more_face, seed_more_jobs, seed_more_market
from tools.seed_world import seed_chat, seed_games, seed_meetings, seed_roulette

GROUPS = (
    ("jobs", "job", seed_jobs),
    ("more jobs", "job", seed_more_jobs),
    ("market", "market", seed_market),
    ("more market", "market", seed_more_market),
    ("face", "face", seed_face),
    ("more face", "face", seed_more_face),
    ("chat rooms", "chat", seed_chat),
    ("private talk", "chat", seed_more_dms),
    ("social", "chat", seed_friends),
    ("meetings", "chat", seed_meetings),
    ("games", "werewolf", seed_games),
    ("roulette", "roulette", seed_roulette),
)

WATCHED = {
    "jobs": (Skill, JobDescription, JobApplicant),
    "more jobs": (Skill, JobDescription, JobApplicant),
    "more market": (Product, CartItem, Order, Comment),
    "more face": (Measurement,),
    "private talk": (Room, RoomMember, Message),
    "market": (Product, CartItem, Order, Comment),
    "chat rooms": (Room, RoomMember, Message),
    "meetings": (Meeting,),
    "games": (Game,),
    "roulette": (Wallet, Spin),
    "face": (Measurement,),
    "social": (Edge, Notification, Report),
}
