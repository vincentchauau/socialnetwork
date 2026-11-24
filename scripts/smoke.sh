#!/usr/bin/env bash
# Checks the running stack in one go: every page answers, every table of every app lists without a server error (as an admin and as a person),
# and the frontend types and tests pass. Run it after a change and before asking anyone to look.
#   bash scripts/smoke.sh            everything
#   bash scripts/smoke.sh --quick    pages and tables only (no types or tests)
set -u
cd "$(dirname "$0")/.."
BASE="${BASE_URL:-http://localhost:8080}"
BACKEND="${BACKEND_CONTAINER:-socialnetwork-api-backend-1}"
failed=0

echo "== pages"
for path in / /user /forgot-password; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$path")
  [ "$code" = "200" ] || { echo "  FAILED $path -> $code"; failed=1; }
done
for path in /database /login /account /profile; do # the old addresses redirect
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$path")
  [ "$code" = "308" ] || { echo "  FAILED $path -> $code (expected a redirect)"; failed=1; }
done

echo "== tables and routes of the backend"
MSYS_NO_PATHCONV=1 docker exec -u root "$BACKEND" rm -rf /srv/tools_smoke >/dev/null 2>&1
MSYS_NO_PATHCONV=1 docker cp backend/tools/smoke.py "$BACKEND:/srv/smoke_run.py" >/dev/null
MSYS_NO_PATHCONV=1 docker exec -w /srv -e PYTHONPATH=/srv "$BACKEND" python smoke_run.py 2>&1 | grep -v "Warning\|from starlette" || failed=1
[ "${PIPESTATUS[0]}" = "0" ] || failed=1
MSYS_NO_PATHCONV=1 docker exec -u root "$BACKEND" rm -f /srv/smoke_run.py >/dev/null 2>&1

if [ "${1:-}" != "--quick" ]; then
  echo "== frontend types and tests"
  (cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | grep -E "Tests |FAIL") || failed=1
fi

[ "$failed" = "0" ] && echo "ALL GOOD" || { echo "SOMETHING FAILED"; exit 1; }
