"""Who may touch a thing: the rule every app applies to what a person owns.

A stranger gets 404, never 403: saying "this is not yours" would tell them it exists. The owner is a column of the row
(`owner_id`, `seller_id`, `user_id`...): `field` says which.
"""

from fastapi import HTTPException, status

import logging
logger = logging.getLogger(__name__)


def not_found(what: str = "Not found") -> HTTPException:
    try:
        return HTTPException(status.HTTP_404_NOT_FOUND, what)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("not_found failed")
        raise


def is_owner(thing: object | None, user_id: int, field: str = "owner_id") -> bool:
    try:
        return thing is not None and getattr(thing, field) == user_id
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("is_owner failed")
        raise


def ensure_owner(thing, user, field: str = "owner_id", what: str = "Not found"):
    """`thing` when it is the user's (`user` has a `user_id`); else 404 with `what` (the same words as for a thing that is not there)."""
    try:
        if not is_owner(thing, user.user_id, field):
            raise not_found(what)
        return thing
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_owner failed")
        raise
