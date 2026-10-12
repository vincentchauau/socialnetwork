"""Admin commands (run on the server only):

  python -m app.cli promote|demote <username>   grant / revoke the admin role
  python -m app.cli reset-password <username>   set a new password (prompt or stdin) and revoke all sessions
"""

import getpass
import os
import sys
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import DEFAULT_DATABASE_URL, Base, make_engine
from app.migrate import ensure_columns
from app.models import User
from app.passwords import hash_password, password_problem
from app.tokenversion import bump_token_version

COMMANDS = ("promote", "demote", "reset-password")


def read_new_password() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("New password: ")
    return sys.stdin.readline().rstrip("\r\n")


def _open_session() -> Session:
    engine = make_engine(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)
    ensure_columns(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def main(
    argv: list[str],
    read_password: Callable[[], str] = read_new_password,
    open_session: Callable[[], Session] = _open_session,
) -> int:
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
            print(f"Password reset for {username}; all sessions revoked")
            return 0
        user.role = "admin" if command == "promote" else "user"
        if command == "demote":
            bump_token_version(db, user)  # drop sessions that still carry the admin claim
        db.commit()
        print(f"Role of {username} is now {user.role}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
