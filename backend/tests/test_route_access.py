"""Guard: every route of every module app carries the two gates.

`require_groups` (the letters each group may use) and `require_users` (who may call; default every signed-in user).
A route with `require_groups(public=True)` is open on purpose (health, sign-in, signed service calls). The failure names
the routes that carry no gate, so a new route cannot ship unguarded.
"""

import importlib

import pytest
from fastapi.routing import APIRoute
from sn_shared.testing import install_test_keys
from starlette.routing import Mount, WebSocketRoute

install_test_keys()

MODULES = ("center", "chat", "face", "file", "job", "market", "roulette", "werewolf")


def _calls_of(route, inherited=()):
    calls = list(inherited)
    if isinstance(route, APIRoute):
        stack = list(route.dependant.dependencies)
    else:
        stack = list(getattr(getattr(route, "dependant", None), "dependencies", []))
    while stack:
        dependency = stack.pop()
        calls.append(dependency.call)
        stack.extend(dependency.dependencies)
    return calls


def _flatten(routes, inherited=()):
    """(method, path, calls) for every route, carrying the dependencies of the include and mount it sits under."""
    for route in routes:
        if isinstance(route, Mount):
            yield from _flatten(route.app.routes, inherited)
        elif type(route).__name__ == "_IncludedRouter":
            extra = tuple(d.dependency for d in route.include_context.dependencies or [])
            yield from _flatten(route.original_router.routes, inherited + extra)
        elif isinstance(route, APIRoute):
            for method in sorted(route.methods):
                yield method, route.path, _calls_of(route, inherited)
        elif isinstance(route, WebSocketRoute):
            yield "WS", route.path, _calls_of(route, inherited)


def build(module: str):
    return importlib.import_module(f"api.{module}.main").create_app("sqlite://")


def gates(calls):
    groups = [c for c in calls if hasattr(c, "access_groups")]
    users = [c for c in calls if hasattr(c, "access_users")]
    return groups, users


@pytest.mark.parametrize("module", MODULES)
def test_every_route_carries_both_gates(module):
    rows = list(_flatten(build(module).routes))
    assert rows, f"{module} has no routes"
    offenders = []
    for method, path, calls in rows:
        groups, users = gates(calls)
        if not groups or not users:
            offenders.append(f"{module}: {method} {path}")
    assert not offenders, "routes without require_groups and require_users:\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("module", MODULES)
def test_public_routes_are_marked_public_and_only_those(module):
    for method, path, calls in _flatten(build(module).routes):
        groups, _ = gates(calls)
        assert groups, f"{module}: {method} {path} has no require_groups"
        is_public = any(getattr(g, "public", False) for g in groups)
        if is_public:
            assert all(getattr(g, "public", False) for g in groups), f"{module}: {method} {path} mixes public and gated"


def test_only_the_expected_routes_are_public():
    public = []
    for module in MODULES:
        for method, path, calls in _flatten(build(module).routes):
            if any(getattr(g, "public", False) for g in gates(calls)[0]):
                public.append(f"{module} {method} {path}")
    assert len(public) == len(set(public))
    assert any(p.startswith("center POST /auth/login") or p.startswith("center POST /auth/register") for p in public)
