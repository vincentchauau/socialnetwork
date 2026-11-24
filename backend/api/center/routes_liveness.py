"""GET/POST /auth/liveness/challenge: a random action challenge for the webcam methods."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.center.deps import check_origin, client_ip, too_many
from api.center.liveness import CHALLENGE_TTL_SECONDS, issue_token, new_actions
from api.center.routes_biometrics import ensure_biometrics

router = APIRouter(
    prefix="/auth", tags=["liveness"], dependencies=[Depends(ensure_biometrics), Depends(check_origin)]
)


class LivenessChallenge(BaseModel):
    challenge_token: str
    actions: list[str]
    expires_in: int


@router.get("/liveness/challenge", response_model=LivenessChallenge)
def liveness_challenge_get(request: Request) -> LivenessChallenge:
    return liveness_challenge(request)


@router.post("/liveness/challenge", response_model=LivenessChallenge)
def liveness_challenge_post(request: Request) -> LivenessChallenge:
    return liveness_challenge(request)


def liveness_challenge(request: Request) -> LivenessChallenge:
    if not request.app.state.liveness_throttle.check_and_record(client_ip(request)):
        raise too_many()
    actions = new_actions()
    return LivenessChallenge(
        challenge_token=issue_token(actions), actions=actions, expires_in=CHALLENGE_TTL_SECONDS
    )
