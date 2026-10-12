from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Posting
from sn_shared.security import TokenPayload

MAX_LIST_ITEMS = 100


def get_posting(db: Session, posting_id: int) -> Posting:
    posting = db.get(Posting, posting_id)
    if posting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return posting


def get_visible_posting(db: Session, posting_id: int, user: TokenPayload) -> Posting:
    """A posting the caller may see: any open one, or their own in any state."""
    posting = get_posting(db, posting_id)
    if posting.status != "open" and posting.owner_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return posting


def require_owner(posting: Posting, user: TokenPayload) -> Posting:
    if posting.owner_id != user.user_id:
        # 404, not 403: do not reveal that the resource exists to non-owners
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return posting
