"""Fill the empty tables of the platform with coherent Vietnamese demo data, through the modules' own models and helpers.

    python -m tools.seed_demo --url postgresql://user:pass@db/app            # from backend/ (in the container: /srv)
    python -m tools.seed_demo --dry-run                                      # counts only, nothing is kept
    python -m tools.seed_demo --embedder dummy                               # hash embeddings instead of AI_PROVIDER's

Database: `--url`, else `DATABASE_URL` (one database for every module).
Owners, sellers, employers and learners are read from `users`; nothing existing is changed. Each group is skipped when its
marker rows (the fixed titles, names, filenames... of this file) are already there, so a second run adds nothing.
"""

import argparse
import os
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):  # run as a script: put backend/ on the path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from sn_shared import comments as shared_comments
from sn_shared import skills as shared_skills
from sn_shared.db import make_engine

from tools import seed_groups as groups
from tools.seed_cast import Cast, load_people
from tools.seed_env import Env

MODULES = ("center", "job", "market", "face", "chat", "werewolf", "roulette")


def database_url(module: str, url: str | None) -> str:
    chosen = url or os.environ.get("DATABASE_URL")
    if not chosen:
        raise SystemExit(f"No database for {module}: give --url, or set DATABASE_URL")
    return chosen


@dataclass
class Result:
    counts: Counter = field(default_factory=Counter)  # table -> rows added
    skipped: dict[str, str] = field(default_factory=dict)  # group -> why nothing was added


def create_tables(module: str, engine: Engine) -> None:
    """Only the tables that are missing (an existing table is never touched)."""
    if module == "job":
        from api.job.db import Base
        import api.job.models  # noqa: F401
        Base.metadata.create_all(engine)
        shared_skills.ensure_tables(engine)
    elif module == "market":
        from api.market.db import Base
        import api.market.models  # noqa: F401
        Base.metadata.create_all(engine)
        shared_comments.ensure_table(engine)
    elif module == "face":
        from api.face.db import Base
        import api.face.models  # noqa: F401
        Base.metadata.create_all(engine)
    elif module == "chat":
        from api.chat.social.models import Base
        Base.metadata.create_all(engine)
    elif module in ("werewolf", "roulette"):
        import importlib

        importlib.import_module(f"api.{module}.models")
        importlib.import_module(f"api.{module}.db").Base.metadata.create_all(engine)


def tables_seed_demo(db: Session, models: tuple) -> dict[str, int]:
    return {m.__tablename__: db.scalar(select(func.count()).select_from(m)) or 0 for m in models}


def seed(url: str | None = None, dry_run: bool = False, embedder: str = "env", now: datetime | None = None, seed_value: int = 20260101, only: frozenset[str] | None = None) -> Result:
    """`only` names the groups to run (all of `seed_groups.GROUPS` when None)."""
    now = now or datetime.now(timezone.utc)
    engines: dict[str, Engine] = {}
    by_url: dict[str, Engine] = {}
    for module in MODULES:
        target = database_url(module, url)
        engines[module] = by_url.setdefault(target, make_engine(target))
    if not dry_run:
        for module in MODULES[1:]:
            create_tables(module, engines[module])
    with Session(engines["center"]) as db:
        people = load_people(db)
    if not people:
        raise SystemExit("No users to own the demo data: the users table is empty")
    cast = Cast(people, random.Random(seed_value))
    env = Env(now=now, rng=random.Random(seed_value + 1), cast=cast, embedder=embedder, engines=engines)
    result = Result()
    for name, module, run in groups.GROUPS:
        if only is not None and name not in only:
            continue
        try:
            with Session(engines[module]) as db:
                before = tables_seed_demo(db, groups.WATCHED[name])
                reason = run(env, db)
                if reason:
                    db.rollback()
                    result.skipped[name] = reason
                    continue
                db.flush()
                after = tables_seed_demo(db, groups.WATCHED[name])
                result.counts.update({table: after[table] - before[table] for table in after})
                db.rollback() if dry_run else db.commit()
        except Exception as error:  # a group that cannot run must not hide what the others did
            if os.environ.get("SEED_DEMO_RAISE"):
                raise
            result.skipped[name] = f"failed: {type(error).__name__}: {error}"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill the empty tables with Vietnamese demo data.")
    parser.add_argument("--url", help="the database URL (default: DATABASE_URL)")
    parser.add_argument("--dry-run", action="store_true", help="work out what would be added and keep nothing")
    parser.add_argument("--embedder", choices=("env", "dummy"), default="env", help="embeddings of the documents: the AI_PROVIDER one, or hashed words")
    args = parser.parse_args(argv)
    result = seed(args.url, args.dry_run, args.embedder)
    print(("Would add" if args.dry_run else "Added") + " rows:")
    for table, count in sorted(result.counts.items()):
        if count:
            print(f"  {table:<22}{count}")
    for group, reason in result.skipped.items():
        print(f"  skipped {group}: {reason}")
    if not any(result.counts.values()):
        print("  (nothing)")
    return 1 if any(reason.startswith("failed") for reason in result.skipped.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
