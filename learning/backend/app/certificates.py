import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Course, Enrollment, utcnow
from app.schemas import CertificateOut, PublicCertificateOut
from app.services import compute_progress, require_enrollment, visible_course
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

CODE_BYTES = 16  # 128 bits of randomness
CODE_PATTERN = r"^[A-Za-z0-9_-]{16,64}$"


@router.get("/courses/{course_id}/certificate", response_model=CertificateOut)
def get_certificate(
    course_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CertificateOut:
    course = visible_course(db, course_id, user)
    enrollment = require_enrollment(db, course.id, user.user_id)
    if enrollment.certificate_code is None or enrollment.completed_at is None:
        if not compute_progress(db, course, user.user_id).completed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Finish every lesson and pass every quiz to earn the certificate",
            )
        enrollment.certificate_code = secrets.token_urlsafe(CODE_BYTES)
        enrollment.completed_at = utcnow()
        db.commit()
    return CertificateOut(
        learner=enrollment.username,
        course=course.title,
        completed_at=enrollment.completed_at,
        code=enrollment.certificate_code,
    )


@router.get("/certificates/{code}", response_model=PublicCertificateOut)
def verify_certificate(
    code: Annotated[str, Path(pattern=CODE_PATTERN)], db: Session = Depends(get_db)
) -> PublicCertificateOut:
    """Public: confirms a code is genuine and reveals only name, course and date."""
    enrollment = db.scalar(select(Enrollment).where(Enrollment.certificate_code == code))
    if enrollment is None or enrollment.completed_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificate not found")
    course = db.get(Course, enrollment.course_id)
    return PublicCertificateOut(
        learner=enrollment.username,
        course=course.title if course else "",
        completed_at=enrollment.completed_at,
    )
