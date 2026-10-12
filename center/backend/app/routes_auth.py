import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas import Credentials, UserOut
from sn_shared import COOKIE_NAME, create_token, hash_password, verify_password
from sn_shared.deps import get_current_user
from sn_shared.security import DEFAULT_TTL_SECONDS, TokenPayload

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against when the username is unknown, so response time does not
# reveal whether an account exists.
_DUMMY_HASH = hash_password("dummy-password")


def _set_auth_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_token(user.id, user.username),
        max_age=DEFAULT_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("COOKIE_SECURE") == "1",
        path="/",
    )


def _client_ip(request: Request) -> str:
    # Behind the gateway uvicorn runs with --proxy-headers, so this is the real client.
    return request.client.host if request.client else "unknown"


def _too_many() -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try later")


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def register(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    throttle = request.app.state.register_throttle
    ip = _client_ip(request)
    if throttle.is_blocked(ip):
        raise _too_many()
    throttle.record(ip)
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken") from None
    _set_auth_cookie(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    ip = _client_ip(request)
    account_key = f"{ip}|{body.username}"
    account_throttle = request.app.state.login_throttle
    ip_throttle = request.app.state.login_ip_throttle
    if account_throttle.is_blocked(account_key) or ip_throttle.is_blocked(ip):
        raise _too_many()
    user = db.scalar(select(User).where(User.username == body.username))
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        account_throttle.record(account_key)
        ip_throttle.record(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    account_throttle.reset(account_key)
    _set_auth_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(current: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    user = db.get(User, current.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user
