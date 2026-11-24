"""Smoke test of the running backend: every table of every app, as an admin and as a person, and the plain GET routes.

Run inside the backend container (`scripts/smoke.sh` does): `python -m tools.smoke`. It calls each module in process with a fake signed-in person,
so it needs the database with its data but no password. It fails (exit 1) on any server error (5xx), which is what a table whose rows do not fit
its response model gives (a seeder that left a field out, a column that was dropped).
"""

import sys
import time

from fastapi.testclient import TestClient
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload
from starlette.routing import Mount

from api.main import app

PERSON_ID = 301
SKIPPED = ("/openapi", "/docs", "/redoc", "/health", "/internal", "/admin", "/records", "/data")


def _modules() -> list[Mount]:
    return [route for route in app.routes if isinstance(route, Mount)]


def _tables(client: TestClient, base: str) -> list[str]:
    reply = client.get(f"/{base}/tables")
    return [table["name"] for table in reply.json()] if reply.status_code == 200 else []


def check(group: str) -> list[str]:
    """The failures (server errors) found as a person of `group`; also prints what was checked."""
    person = TokenPayload(user_id=PERSON_ID, username="smoke", expires_at=int(time.time()) + 3600, group=group)
    failures: list[str] = []
    tables = routes = 0
    for module in _modules():
        module.app.dependency_overrides[get_current_user] = lambda: person
        client = TestClient(module.app, raise_server_exceptions=False)
        for base in ("records", "data"):
            if client.get(f"/{base}/tables").status_code >= 500:
                failures.append(f"{module.path}/{base}/tables")
            for name in _tables(client, base):
                tables += 1
                if client.get(f"/{base}/{name}", params={"limit": 50}).status_code >= 500:
                    failures.append(f"{module.path}/{base}/{name}")
        for route in module.app.routes:
            path = getattr(route, "path", "")
            if "GET" not in (getattr(route, "methods", None) or ()) or "{" in path or path.startswith(SKIPPED):
                continue
            routes += 1
            if client.get(path).status_code >= 500:
                failures.append(f"{module.path}{path}")
    print(f"{group}: {tables} tables and {routes} plain routes checked, {len(failures)} server errors")
    return failures


def main() -> int:
    failures = check("admin") + check("user")
    for failure in failures:
        print("  FAILED", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
