"""The Werewolf game: the rules (engine), the rooms of a game (in memory), and the results (stored).

Its routes are those of its own module (REST, and the WebSocket `/ws/{code}`). The state it keeps on the app is `ww_hub`, `ww_limits` and `ww_store`.
The chat asks it for the game of a room with a signed call (`internal`).
"""

from api.werewolf.hub import GameHub
from api.werewolf.limits import UserLimits
from api.werewolf.migrate import ensure_columns
from api.werewolf.routes import router
from api.werewolf.service import reaper_loop, tick_loop
from api.werewolf.snapshots import restore
from api.werewolf.store import RoomStore
from api.werewolf.ws import router as ws_router

__all__ = ["GameHub", "RoomStore", "UserLimits", "ensure_columns", "reaper_loop", "restore", "router", "tick_loop", "ws_router"]
