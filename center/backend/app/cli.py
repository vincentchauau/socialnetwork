"""Admin commands (run on the server only):

  python -m app.cli promote|demote <username>   grant / revoke the admin role
  python -m app.cli reset-password <username>   set a new password (prompt or stdin) and revoke all sessions
  python -m app.cli gen-jwt-key                 print a new Ed25519 access-token keypair (private PEM, public PEM, kid)
"""

import getpass
import os
import sys
from typing import Callable

from sn_shared import jwtkeys
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import DEFAULT_DATABASE_URL, Base, make_engine
from app.migrate import ensure_columns, force_relogin, sessions_table_is_new
from app.models import User
from app.passwords import hash_password, password_problem
from app.config import Settings
from app.tokenversion import bump_token_version, publish_token_version

COMMANDS = ("promote", "demote", "reset-password")


def read_new_password() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("New password: ")
    return sys.stdin.readline().rstrip("\r\n")


def _publish(user: User) -> None:
    """Tell the other apps right away (needs the same env as the server: REDIS_URL, ACCESS_TOKEN_MINUTES)."""
    try:
        publish_token_version(user, Settings.from_env())
    except RuntimeError as exc:  # unusable settings: the revocation then waits for the tokens to expire
        print(f"Warning: other apps were not notified ({exc})")


def _open_session() -> Session:
    engine = make_engine(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    first_with_sessions = sessions_table_is_new(engine)
    Base.metadata.create_all(engine)
    ensure_columns(engine)
    if first_with_sessions:
        force_relogin(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def gen_jwt_key() -> int:
    """Print a fresh keypair: the private key goes to center only, the public key to every app."""
    private, public, kid = jwtkeys.generate_keypair()
    print("# JWT_PRIVATE_KEY (center only; keep secret, e.g. save as secrets/jwt_private.pem):")
    print(private.strip())
    print("\n# JWT_PUBLIC_KEYS (every app; append to the existing keys when rotating):")
    print(public.strip())
    print(f"\n# kid (the JWT_KEY_ID default): {kid}")
    return 0


def main(
    argv: list[str],
    read_password: Callable[[], str] = read_new_password,
    open_session: Callable[[], Session] = _open_session,
) -> int:
    if argv == ["gen-jwt-key"]:
        return gen_jwt_key()
    if len(argv) != 2 or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    command, username = argv[0], argv[1].strip().lower()
    with open_session() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            print("User not found")
            return 1
        if command == "reset-password":
            new = read_password()
            problem = password_problem(new, username)
            if problem:
                print(problem)
                return 1
            user.password_hash = hash_password(new)
            bump_token_version(db, user)
            db.commit()
            _publish(user)
            print(f"Password reset for {username}; all sessions revoked")
            return 0
        user.role = "admin" if command == "promote" else "user"
        if command == "demote":
            bump_token_version(db, user)  # drop sessions that still carry the admin claim
        db.commit()
        if command == "demote":
            _publish(user)
        print(f"Role of {username} is now {user.role}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
