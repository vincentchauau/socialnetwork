"""The people side of the chat over HTTP: my profile, people, friends, blocks, reports, notifications."""

from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sn_shared.deps import get_current_user, require_groups
from sn_shared.directory import Person
from sn_shared.security import TokenPayload
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.chat.db import get_db
from api.chat.social import companions, service
from api.chat.social.models import Report

from api.chat.routes_common import new_router
from api.chat.schemas_people import (
    PersonOut,
    ReportIn,
    ReportOut,
    ReportReview,
)

LIST_LIMIT = 100
router = new_router()

Db = Annotated[Session, Depends(get_db)]
Me = Annotated[TokenPayload, Depends(get_current_user)]


def refuse(error: service.Refused) -> HTTPException:
    return HTTPException(error.status, str(error))


def person_out(db: Session, me: int, person: Person, *, friends: set[int] | None = None) -> PersonOut:
    """A person as `me` may see them: the username to everyone, and of the profile only what its owner made public (a virtual person
    shows all of it); the summary is for friends too, unless its owner made it public. Nobody sees more of themselves than they chose
    to show others, except themselves."""
    friend = person.user_id in friends if friends is not None else service.relation(db, me, person.user_id) == service.FRIENDS
    view = person.view(own=person.user_id == me)
    readable = person.user_id == me or friend or view.summary_public
    return PersonOut(
        user_id=person.user_id, username=person.username, display_name=view.display_name, headline=view.headline,
        region=view.region, avatar=view.avatar, summary=view.summary if readable else None,
        relation=service.relation(db, me, person.user_id) if person.user_id != me else service.NONE,
        blocked=service.blocked_by(db, me, person.user_id),
        virtual=person.is_virtual,
        age=date.today().year - view.birth_year if view.birth_year else None,
        interests=view.interests,
        companion=person.is_virtual and companions.is_companion(db, me, person.user_id),
    )  # fmt: skip


def known(db: Session, user_id: int) -> Person:
    person = db.get(Person, user_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    return person


def other_person(db: Session, me: TokenPayload, user_id: int) -> Person:
    """The other person of an action, who must exist and not have blocked me (it looks like they do not exist)."""
    person = known(db, user_id)
    if service.blocked_between(db, me.user_id, user_id) and not service.blocked_by(db, me.user_id, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    return person


# ---- me --------------------------------------------------------------------------------------------------------


# ---- people ----------------------------------------------------------------------------------------------------


@router.get("/people/{username}", response_model=PersonOut)
def read_person(username: str, request: Request, user: Me, db: Db) -> PersonOut:
    person = service.person_by_name(db, username)
    if person is None or (person.user_id != user.user_id and service.blocked_between(db, user.user_id, person.user_id) and not service.blocked_by(db, user.user_id, person.user_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    return person_out(db, user.user_id, person)


# ---- friends ---------------------------------------------------------------------------------------------------


def _mine(db: Session, user: TokenPayload) -> Person:
    return service.actor_of(db, user.user_id, user.username)  # type: ignore[return-value]


@router.post("/friends/{user_id}", response_model=PersonOut)
def ask(user_id: int, request: Request, user: Me, db: Db) -> PersonOut:
    me = _mine(db, user)
    other = other_person(db, user, user_id)
    try:
        service.request_friendship(db, me, other)
    except service.Refused as error:
        db.rollback()
        raise refuse(error) from None
    db.commit()
    return person_out(db, user.user_id, other)


@router.post("/friends/{user_id}/accept", response_model=PersonOut)
def accept(user_id: int, request: Request, user: Me, db: Db) -> PersonOut:
    me = _mine(db, user)
    other = other_person(db, user, user_id)
    try:
        service.accept(db, me, other)
    except service.Refused as error:
        db.rollback()
        raise refuse(error) from None
    db.commit()
    return person_out(db, user.user_id, other)


@router.post("/friends/{user_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline(user_id: int, user: Me, db: Db) -> None:
    me = _mine(db, user)
    try:
        service.decline(db, me, known(db, user_id))
    except service.Refused as error:
        db.rollback()
        raise refuse(error) from None
    db.commit()


@router.delete("/friends/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfriend(user_id: int, user: Me, db: Db) -> None:
    """Stop being friends, or take back a request I made. (Nothing to do if there was nothing.)"""
    service.drop_relationship(db, user.user_id, user_id)
    db.commit()


# ---- blocks ----------------------------------------------------------------------------------------------------


@router.post("/blocks/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def block(user_id: int, user: Me, db: Db) -> None:
    if user_id == user.user_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose someone else")
    known(db, user_id)
    service.block(db, user.user_id, user_id)
    db.commit()


@router.delete("/blocks/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unblock(user_id: int, user: Me, db: Db) -> None:
    service.unblock(db, user.user_id, user_id)
    db.commit()


# ---- reports ---------------------------------------------------------------------------------------------------


@router.post("/reports", status_code=status.HTTP_201_CREATED, response_model=ReportOut)
def report(body: ReportIn, user: Me, db: Db) -> Report:
    try:
        row, _created = service.report(db, user.user_id, body.target_type, body.target_id, body.reason, body.details)
    except service.Refused as error:
        db.rollback()
        raise refuse(error) from None
    db.commit()
    return row


@router.get("/reports/mine", response_model=list[ReportOut])
def my_reports(user: Me, db: Db, limit: Annotated[int, Query(ge=1, le=LIST_LIMIT)] = 50) -> list[Report]:
    """The reports I made that nobody has looked at yet: each can be taken back."""
    return list(db.scalars(select(Report).where(Report.reporter_id == user.user_id, Report.status == "open").order_by(Report.id.desc()).limit(limit)))


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def unreport(report_id: int, user: Me, db: Db) -> None:
    """Take back my own report, while it is still open (one that was looked at stays as it was)."""
    row = db.get(Report, report_id)
    if row is None or row.reporter_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    if row.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "The report was looked at already")
    db.delete(row)
    db.commit()


administrator = require_groups(admin=True, moderator=True)  # the reports queue: only admins and moderators; users are refused here too


@router.get("/reports", response_model=list[ReportOut])
def reports(
    db: Db, _admin: Annotated[TokenPayload, Depends(administrator)],
    status_filter: Annotated[str, Query(alias="status", pattern="^(open|reviewed|actioned)$")] = "open",
    limit: Annotated[int, Query(ge=1, le=LIST_LIMIT)] = 50,
) -> list[Report]:
    return list(db.scalars(select(Report).where(Report.status == status_filter).order_by(Report.id.desc()).limit(limit)))


@router.patch("/reports/{report_id}", response_model=ReportOut)
def review(report_id: int, body: ReportReview, db: Db, _admin: Annotated[TokenPayload, Depends(administrator)]) -> Report:
    row = db.get(Report, report_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    row.status = body.status
    db.commit()
    return row


# ---- notifications ---------------------------------------------------------------------------------------------


# ---- companions: virtual people drawn at random from the pool --------------------------------------------------

