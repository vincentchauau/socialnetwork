"""GET/POST /auth/liveness/challenge: a random action challenge for the webcam methods."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.deps import check_origin, client_ip, too_many
from app.liveness import CHALLENGE_TTL_SECONDS, issue_token, new_actions
from app.routes_biometrics import require_biometrics

liveness_router = APIRouter(
    prefix="/auth", tags=["liveness"], dependencies=[Depends(require_biometrics), Depends(check_origin)]
)


class LivenessChallenge(BaseModel):
    challenge_token: str
    actions: list[str]
    expires_in: int


@liveness_router.get("/liveness/challenge", response_model=LivenessChallenge)
def liveness_challenge_get(request: Request) -> LivenessChallenge:
    return liveness_challenge(request)


@liveness_router.post("/liveness/challenge", response_model=LivenessChallenge)
def liveness_challenge_post(request: Request) -> LivenessChallenge:
    return liveness_challenge(request)


def liveness_challenge(request: Request) -> LivenessChallenge:
    if not request.app.state.liveness_throttle.check_and_record(client_ip(request)):
        raise too_many()
    actions = new_actions()
    return LivenessChallenge(
        challenge_token=issue_token(actions), actions=actions, expires_in=CHALLENGE_TTL_SECONDS
    )
