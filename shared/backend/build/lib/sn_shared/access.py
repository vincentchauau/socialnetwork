"""Who may touch a thing: the rule every app applies to what a person owns.

A stranger gets 404, never 403: saying "this is not yours" would tell them it exists. The owner is a column of the row
(`owner_id`, `seller_id`, `user_id`...): `field` says which.
"""

from fastapi import HTTPException, status


def not_found(what: str = "Not found") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, what)


def is_owner(thing: object | None, user_id: int, field: str = "owner_id") -> bool:
    return thing is not None and getattr(thing, field) == user_id


def ensure_owner(thing, user, field: str = "owner_id", what: str = "Not found"):
    """`thing` when it is the user's (`user` has a `user_id`); else 404 with `what` (the same words as for a thing that is not there)."""
    if not is_owner(thing, user.user_id, field):
        raise not_found(what)
    return thing
