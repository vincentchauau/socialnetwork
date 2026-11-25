"""Admin commands (run on the server only):

  python -m app.cli promote|demote <username>   grant / revoke the admin group (demote: back to user)
  python -m app.cli moderate|unmoderate <username>   grant / revoke the moderator group (reports queue only)
  python -m app.cli set-group <username> <user|moderator|admin>
  python -m app.cli reset-password <username>   set a new password (prompt or stdin) and revoke all sessions
  python -m app.cli seed-virtual                add the missing virtual people of the pool (safe to repeat)
  python -m app.cli gen-jwt-key                 write a new Ed25519 access-token keypair to files (private PEM, public PEM, kid)
"""

import getpass
import logging
import os
import sys
from pathlib import Path
from typing import Callable

from sn_shared import jwtkeys
from sn_shared.deps import GROUP_ADMIN, GROUP_MODERATOR, GROUP_USER, GROUPS
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from api.center.db import DEFAULT_DATABASE_URL, Base, make_engine
from api.center.handles import key_of
from api.center.migrate import ensure_columns, force_relogin, sessions_table_is_new
from api.center.models import User
from api.center.passwords import hash_password, password_problem
from api.center.config import Settings
from api.center.virtual_seed import POOL_SIZE, seed_pool
from api.center.tokenversion import bump_token_version, publish_token_version

log = logging.getLogger("center.cli")

GROUP_COMMANDS = {"promote": GROUP_ADMIN, "demote": GROUP_USER, "moderate": GROUP_MODERATOR, "unmoderate": GROUP_USER}
COMMANDS = (*GROUP_COMMANDS, "set-group", "reset-password")


def read_new_password() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("New password: ")
    return sys.stdin.readline().rstrip("\r\n")


def _publish(user: User) -> None:
    """Tell the other apps right away (needs the same env as the server: REDIS_URL, ACCESS_TOKEN_MINUTES)."""
    try:
        publish_token_version(user, Settings.from_env())
    except RuntimeError as exc:  # unusable settings: the revocation then waits for the tokens to expire
        log.warning("other apps were not notified: %s", exc)


def _open_session() -> Session:
    engine = make_engine(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    first_with_sessions = sessions_table_is_new(engine)
    Base.metadata.create_all(engine)
    ensure_columns(engine)
    if first_with_sessions:
        force_relogin(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def gen_jwt_key(out_dir: str = "secrets") -> int:
    """Write a fresh keypair to files: the private key goes to center only, the public key to every app.

    The private key is never printed (a terminal keeps its history); the files are created with owner-only rights where the system allows.
    """
    private, public, kid = jwtkeys.generate_keypair()
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    private_path = folder / "jwt_private.pem"
    public_path = folder / "jwt_public_keys.pem"
    private_path.write_text(private.strip() + "\n", encoding="utf-8")
    os.chmod(private_path, 0o600)
    public_path.write_text(public.strip() + "\n", encoding="utf-8")
    print(f"private key: {private_path} (center only; keep it secret)")
    print(f"public keys: {public_path} (every app; append to the existing keys when rotating)")
    print(f"kid (the JWT_KEY_ID default): {kid}")
    return 0


def main(
    argv: list[str],
    read_password: Callable[[], str] = read_new_password,
    open_session: Callable[[], Session] = _open_session,
) -> int:
    if argv == ["gen-jwt-key"]:
        return gen_jwt_key()
    if argv == ["seed-virtual"]:
        with open_session() as db:
            added = seed_pool(db)
            db.commit()
        print(f"Added {added} virtual people (the pool holds up to {POOL_SIZE})")
        return 0
    wanted = argv[2] if len(argv) == 3 and argv[0] == "set-group" else None
    if argv[:1] == ["set-group"]:
        if wanted not in GROUPS:
            print(__doc__)
            return 2
    elif len(argv) != 2 or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    command, username = argv[0], key_of(argv[1])
    with open_session() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == username))
        if user is None:
            print("User not found")
            return 1
        if command == "reset-password":
            new = read_password()
            problem = password_problem(new)
            if problem:
                print(problem)
                return 1
            user.password_hash = hash_password(new)
            bump_token_version(db, user)
            db.commit()
            _publish(user)
            print(f"Password reset for {user.username}; all sessions revoked")
            return 0
        new_group = wanted if command == "set-group" else GROUP_COMMANDS[command]
        lowered = GROUPS.index(new_group) < GROUPS.index(user.group if user.group in GROUPS else GROUP_USER)
        user.group = new_group
        revoke = lowered or command == "demote"
        if revoke:
            bump_token_version(db, user)  # drop sessions that still carry the higher group claim
        db.commit()
        if revoke:
            _publish(user)
        print(f"Group of {user.username} is now {user.group}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
