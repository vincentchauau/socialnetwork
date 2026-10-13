from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Measurement
from app.schemas import MeasurementIn, MeasurementOut
from app.security import check_origin
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

MAX_PER_USER = 200


def rate_limited(request: Request, user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if not request.app.state.limiter.allow(user.user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down")
    return user


def _out(row: Measurement) -> dict:
    return MeasurementOut.model_validate(row).model_dump(by_alias=True, mode="json")


@router.post(
    "/measurements",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_origin)],
)
def create_measurement(
    body: MeasurementIn,
    user: TokenPayload = Depends(rate_limited),
    db: Session = Depends(get_db),
) -> dict:
    row = Measurement(user_id=user.user_id, **body.model_dump())
    db.add(row)
    db.flush()
    overflow = db.scalars(
        select(Measurement.id)
        .where(Measurement.user_id == user.user_id)
        .order_by(Measurement.id.desc())
        .offset(MAX_PER_USER)
    ).all()
    if overflow:
        db.execute(delete(Measurement).where(Measurement.id.in_(overflow)))
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/measurements")
def list_measurements(
    limit: Annotated[int, Query(ge=1, le=MAX_PER_USER)] = 50,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(Measurement)
        .where(Measurement.user_id == user.user_id)
        .order_by(Measurement.id.desc())
        .limit(limit)
    ).all()
    return [_out(row) for row in rows]


@router.delete(
    "/measurements/{measurement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_origin)],
)
def delete_measurement(
    measurement_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = db.get(Measurement, measurement_id)
    if row is None or row.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Measurement not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/measurements",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_origin)],
)
def delete_all_measurements(
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    db.execute(delete(Measurement).where(Measurement.user_id == user.user_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
