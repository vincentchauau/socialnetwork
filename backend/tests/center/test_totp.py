"""TOTP second factor, recovery codes, the passkey cap and the migration for them."""

import logging
import re
import time
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from api.center import totp
from api.center.config import ConfigError, Settings
from api.center.crypto import TemplateCipher
from api.center.main import create_app
from api.center.models import Passkey, RecoveryCode, User
from tests.center.helpers import CREDS, csrf, register, grant_fresh
from tests.center.mail_helpers import PW, last_mail, set_user, user_row, verified_account
from tests.center.test_biometrics import FACE, VOICE, enroll, files, set_2fa
from tests.center.test_migrate import make_old_db
from tests.center.test_passkeys import link, passkey_only
from tests.center.webauthn_helper import SoftAuthenticator

GENERIC = {"detail": "Invalid code"}
CODE_FORMAT = re.compile(r"^[a-z2-7]{4}-[a-z2-7]{4}-[a-z2-7]{2}$")


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, steps: int = 1) -> None:
        self.now += steps * totp.STEP_SECONDS


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(totp, "_now", fake)
    return fake


def code_at(secret: str, clock: Clock, offset: int = 0) -> str:
    return pyotp.TOTP(secret).at(clock.now + offset * totp.STEP_SECONDS)


def setup(client, session, body=PW):
    return client.post("/auth/totp/setup", json=body, headers=csrf(session))


def enable(client, session, code, body=PW):
    response = client.post("/auth/totp/enable", json={"code": code, **body}, headers=csrf(session))
    if response.status_code == 200:
        session["csrf_token"] = response.json()["csrf_token"]  # the session was re-issued, like a frontend would
    return response


def disable(client, session, code, body=PW):
    return client.request("DELETE", "/auth/totp", json={"code": code, **body}, headers=csrf(session))


def regenerate(client, session, code, body=PW):
    return client.post("/auth/totp/recovery-codes", json={"code": code, **body}, headers=csrf(session))


def turn_on(client, session, clock):
    """Run setup + enable. Returns (secret, recovery codes)."""
    secret = setup(client, session).json()["secret"]
    response = enable(client, session, code_at(secret, clock))
    assert response.status_code == 200, response.text
    return secret, response.json()["recovery_codes"]


@pytest.fixture
def account(client, clock):
    """Alice with TOTP on, signed out. (client, session, secret, recovery codes)."""
    session = register(client)
    secret, codes = turn_on(client, session, clock)
    client.cookies.clear()
    return client, session, secret, codes


def challenge(client, creds=CREDS):
    response = client.post("/auth/login", json=creds)
    assert response.status_code == 200, response.text
    return response.json()


def second_step(client, **fields):
    token = fields.pop("mfa_token", None) or challenge(client)["mfa_token"]
    return client.post("/auth/login/totp", json={"mfa_token": token, **fields})


def db_user(client, username="alice") -> User:
    return user_row(client, username)


def recovery_rows(client) -> list[RecoveryCode]:
    with client.app.state.session_factory() as db:
        return list(db.scalars(select(RecoveryCode).order_by(RecoveryCode.id)))


# --- setup ------------------------------------------------------------------------------------------------


def test_setup_returns_secret_and_authenticator_uri(client):
    session = register(client)

    response = setup(client, session)

    body = response.json()
    assert response.status_code == 200 and set(body) == {"secret", "otpauth_uri"}
    parsed = urlparse(body["otpauth_uri"])
    query = parse_qs(parsed.query)
    assert parsed.scheme == "otpauth" and parsed.netloc == "totp" and parsed.path.endswith("Alice")
    assert query["secret"] == [body["secret"]] and query["issuer"] == ["Mạng xã hội"]
    assert query.get("algorithm", ["SHA1"]) == ["SHA1"] and query.get("digits", ["6"]) == ["6"]
    assert query.get("period", ["30"]) == ["30"]
    assert len(body["secret"]) >= 32
    assert db_user(client).totp_enabled is False


def test_secrets_are_stored_encrypted_never_plain(client):
    session = register(client)
    secret = setup(client, session).json()["secret"]
    pending = db_user(client).totp_pending_secret
    assert pending and secret not in pending
    assert totp.unseal(client.app.state.totp_cipher, pending) == secret

    assert enable(client, session, pyotp.TOTP(secret).now()).status_code == 200

    user = db_user(client)
    assert user.totp_pending_secret is None and user.totp_secret == pending
    with client.app.state.session_factory() as db:
        dump = " ".join(str(v) for row in db.execute(text("SELECT * FROM users")) for v in row)
    assert secret not in dump


def test_cipher_uses_data_key_when_set_else_a_jwt_derived_key(monkeypatch):
    key = Fernet.generate_key().decode()
    with_key = totp.make_cipher(Settings(jwt_secret="j" * 40, data_key=key))
    assert totp.unseal(TemplateCipher(key), totp.seal(with_key, "ABC")) == "ABC"
    derived = totp.make_cipher(Settings(jwt_secret="j" * 40))
    assert totp.unseal(with_key, totp.seal(derived, "ABC")) is None  # a different key
    assert totp.unseal(derived, totp.seal(derived, "ABC")) == "ABC"


def test_invalid_data_key_fails_at_startup(monkeypatch):
    monkeypatch.setenv("DATA_KEY", "nope")
    with pytest.raises(ConfigError, match="Fernet"):
        create_app("sqlite://")


def test_setup_needs_login_csrf_and_password(client):
    assert client.post("/auth/totp/setup").status_code == 401
    session = register(client)
    assert client.post("/auth/totp/setup", json=PW).status_code == 403
    assert setup(client, session, {"password": "wrong"}).status_code == 403
    assert setup(client, session, {}).status_code == 403
    assert client.post("/auth/totp/setup", json=PW, headers={**csrf(session), "Origin": "http://evil.example"}).status_code == 403


def test_setup_again_replaces_the_pending_secret(client, clock):
    session = register(client)
    first = setup(client, session).json()["secret"]
    second = setup(client, session).json()["secret"]
    assert first != second
    assert enable(client, session, code_at(first, clock)).status_code == 400
    assert enable(client, session, code_at(second, clock)).status_code == 200


def test_setup_is_409_once_enabled(client, clock):
    session = register(client)
    turn_on(client, session, clock)
    assert setup(client, session).status_code == 409


# --- enable -----------------------------------------------------------------------------------------------


def test_enable_returns_ten_hashed_recovery_codes(client, clock):
    session = register(client)
    secret, codes = turn_on(client, session, clock)

    assert len(codes) == 10 and len(set(codes)) == 10 and all(CODE_FORMAT.match(c) for c in codes)
    rows = recovery_rows(client)
    assert len(rows) == 10 and all(len(r.code_hash) == 64 and r.used_at is None for r in rows)
    stored = {r.code_hash for r in rows}
    assert not stored & set(codes) and not stored & {c.replace("-", "") for c in codes}
    assert stored == {totp.recovery_hash(c) for c in codes}
    me = client.get("/auth/me").json()
    assert me["totp_enabled"] is True and me["recovery_codes_left"] == 10
    assert db_user(client).totp_last_step == int(clock.now // 30)


def test_enable_keeps_the_current_session_alive(client, clock):
    session = register(client)
    turn_on(client, session, clock)
    assert db_user(client).token_version == 1 and client.get("/auth/me").status_code == 200


def test_enable_rejects_wrong_codes_and_missing_setup(client, clock):
    session = register(client)
    assert enable(client, session, "123456").json() == GENERIC  # no pending secret
    secret = setup(client, session).json()["secret"]
    wrong = enable(client, session, "000000" if code_at(secret, clock) != "000000" else "111111")
    assert (wrong.status_code, wrong.json()) == (400, GENERIC)
    assert enable(client, session, "abcdef").status_code == 400
    assert db_user(client).totp_enabled is False


@pytest.mark.parametrize("offset,ok", [(-2, False), (-1, True), (0, True), (1, True), (2, False)])
def test_enable_accepts_one_step_of_drift_each_way(client, clock, offset, ok):
    session = register(client)
    secret = setup(client, session).json()["secret"]
    response = enable(client, session, code_at(secret, clock, offset))
    assert response.status_code == (200 if ok else 400)


def test_enable_twice_is_409_and_needs_the_password(client, clock):
    session = register(client)
    secret, _ = turn_on(client, session, clock)
    assert enable(client, session, code_at(secret, clock)).status_code == 409
    other = register(client, {"username": "Bob", "password": "S3cret-Pass"})
    setup(client, other)
    assert enable(client, other, "123456", {"password": "bad"}).status_code == 403


def test_wrong_codes_on_enable_are_throttled(client):
    session = register(client)
    setup(client, session)
    statuses = [enable(client, session, "000000").status_code for _ in range(7)]
    assert statuses[:5] == [400] * 5 and statuses[5:] == [429] * 2


def test_google_only_account_can_enable_without_a_password(google_client, clock):
    client = google_client
    session = client.post("/auth/google", json={"id_token": "sub-1|jane@example.com"}).json()
    grant_fresh(google_client)
    secret = setup(client, session, {}).json()["secret"]
    assert enable(client, session, code_at(secret, clock), {}).status_code == 200


# --- login: shape ------------------------------------------------------------------------------------------


def test_totp_account_gets_a_challenge_listing_totp(account):
    client = account[0]
    response = client.post("/auth/login", json=CREDS)
    body = response.json()
    assert set(body) == {"mfa_required", "mfa_token", "factors"}
    assert body["mfa_required"] is True and body["factors"] == ["totp"] and "set-cookie" not in response.headers
    assert client.get("/auth/me").status_code == 401


def test_google_login_gets_the_challenge_too(google_client, clock):
    client = google_client
    session = client.post("/auth/google", json={"id_token": "sub-1|jane@example.com"}).json()
    grant_fresh(google_client)
    turn_ok = setup(client, session, {}).json()["secret"]
    assert enable(client, session, code_at(turn_ok, clock), {}).status_code == 200
    client.cookies.clear()

    body = client.post("/auth/google", json={"id_token": "sub-1|jane@example.com"}).json()

    assert body["mfa_required"] is True and body["factors"] == ["totp"]
    clock.advance()
    done = client.post("/auth/login/totp", json={"mfa_token": body["mfa_token"], "code": code_at(turn_ok, clock)})
    assert done.status_code == 200 and done.json()["username"] == "jane"


def test_email_login_gets_the_challenge_too(mail_client, clock):
    from tests.center.test_email_login import ID_ENDPOINT, ask
    from tests.center.mail_helpers import EMAIL, code_of

    session = verified_account(mail_client)
    secret, _ = turn_on(mail_client, session, clock)
    mail_client.cookies.clear()
    ask(mail_client)
    response = mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": code_of(last_mail(mail_client, EMAIL))})
    assert response.json()["factors"] == ["totp"] and "set-cookie" not in response.headers


# --- login: second step -------------------------------------------------------------------------------------


def test_totp_code_completes_login_and_issues_cookies(account, clock):
    client, _, secret, _ = account
    clock.advance()
    response = second_step(client, code=code_at(secret, clock))
    assert response.status_code == 200 and response.json()["username"] == "Alice"
    assert {"sn_token", "sn_refresh"} <= {c.split("=")[0] for c in response.headers.get_list("set-cookie")}
    assert client.get("/auth/me").status_code == 200


def test_a_code_works_once_replay_is_rejected(account, clock):
    client, _, secret, _ = account
    clock.advance()
    code = code_at(secret, clock)
    assert second_step(client, code=code).status_code == 200
    client.cookies.clear()
    replay = second_step(client, code=code)
    assert (replay.status_code, replay.json()) == (401, GENERIC)
    older = second_step(client, code=code_at(secret, clock, -1))
    assert older.status_code == 401
    clock.advance()
    assert second_step(client, code=code_at(secret, clock)).status_code == 200


def test_the_code_used_to_enable_cannot_log_in(account, clock):
    client, _, secret, _ = account
    assert second_step(client, code=code_at(secret, clock)).status_code == 401


def test_step_guard_is_atomic_and_only_moves_forward(client, clock):
    register(client)
    uid = db_user(client).id
    with client.app.state.session_factory() as db:
        assert totp.accept_step(db, uid, 100) is True
        assert totp.accept_step(db, uid, 100) is False
        assert totp.accept_step(db, uid, 99) is False
        assert totp.accept_step(db, uid, 101) is True
        db.commit()
    assert db_user(client).totp_last_step == 101


def test_every_failure_is_the_same_401(account, clock):
    client, session, secret, codes = account
    clock.advance()
    good = code_at(secret, clock)
    assert second_step(client, code=good).status_code == 200
    token = challenge(client)["mfa_token"]
    assert second_step(client, mfa_token=token, recovery_code=codes[0]).status_code == 200  # burns codes[0]
    expired = challenge(client)["mfa_token"]
    results = [
        second_step(client, mfa_token=token, code="000000"),
        second_step(client, mfa_token=token, code=good),  # replay
        second_step(client, mfa_token=token, code="abc"),
        second_step(client, mfa_token=token, code="éééééé"),
        second_step(client, mfa_token=token, recovery_code=codes[0]),  # used
        second_step(client, mfa_token=token, recovery_code="aaaa-bbbb-cc"),
        second_step(client, mfa_token="garbage", code=good),
        second_step(client, mfa_token="garbage", recovery_code=codes[1]),
        second_step(client, mfa_token=session["csrf_token"], code=good),
    ]
    assert {(r.status_code, r.text) for r in results} == {(401, r.text) for r in results[:1]}
    assert results[0].json() == GENERIC
    assert expired  # kept valid on purpose: a failed attempt does not consume the token


def test_mfa_token_for_an_account_with_totp_disabled_meanwhile_is_rejected(account, clock):
    client, _, secret, _ = account
    token = challenge(client)["mfa_token"]
    set_user(client, totp_enabled=False)
    clock.advance()
    response = second_step(client, mfa_token=token, code=code_at(secret, clock))
    assert (response.status_code, response.json()) == (401, GENERIC)


def test_stale_token_version_is_rejected(account, clock):
    client, _, secret, _ = account
    token = challenge(client)["mfa_token"]
    set_user(client, token_version=5)
    clock.advance()
    assert second_step(client, mfa_token=token, code=code_at(secret, clock)).json() == GENERIC


@pytest.mark.parametrize("fields", [{}, {"code": "123456", "recovery_code": "aaaa-bbbb-cc"}])
def test_exactly_one_of_code_or_recovery_code(account, fields):
    client = account[0]
    assert second_step(client, **fields).status_code == 422


def test_wrong_codes_lock_the_account_with_429(account):
    client, _, secret, _ = account
    token = challenge(client)["mfa_token"]
    statuses = [second_step(client, mfa_token=token, code="000000").status_code for _ in range(12)]
    assert statuses[:10] == [401] * 10 and statuses[10:] == [429] * 2


def test_wrong_codes_lock_the_address_even_with_garbage_tokens(account):
    client = account[0]
    statuses = [second_step(client, mfa_token="x", code="000000").status_code for _ in range(22)]
    assert statuses[:20] == [401] * 20 and statuses[20:] == [429] * 2


def test_a_correct_code_clears_the_failure_counters(account, clock):
    client, _, secret, _ = account
    token = challenge(client)["mfa_token"]
    for _ in range(8):
        second_step(client, mfa_token=token, code="000000")
    clock.advance()
    assert second_step(client, mfa_token=token, code=code_at(secret, clock)).status_code == 200
    state = client.app.state
    assert state.totp_login_account_throttle.tracked_keys() == 0 and state.totp_login_ip_throttle.tracked_keys() == 0


# --- recovery codes -----------------------------------------------------------------------------------------


def test_recovery_code_logs_in_once_and_keeps_totp_on(account, caplog):
    client, _, _, codes = account
    caplog.set_level(logging.INFO, logger="auth.audit")

    first = second_step(client, recovery_code=codes[0])
    client.cookies.clear()
    again = second_step(client, recovery_code=codes[0])

    assert first.status_code == 200 and (again.status_code, again.json()) == (401, GENERIC)
    assert any(r.levelno == logging.WARNING and "recovery code used" in r.getMessage() for r in caplog.records)
    assert codes[0] not in caplog.text
    user = db_user(client)
    assert user.totp_enabled is True and len(recovery_rows(client)) == 10
    me = second_step(client, recovery_code=codes[1])  # logs in again, session cookies set
    assert me.status_code == 200
    assert client.get("/auth/me").json()["recovery_codes_left"] == 8


def test_recovery_code_is_forgiving_about_case_and_dashes(account):
    client, _, _, codes = account
    assert second_step(client, recovery_code=codes[0].upper().replace("-", " ")).status_code == 200


def test_consume_guard_lets_exactly_one_caller_win(client, clock):
    session = register(client)
    _, codes = turn_on(client, session, clock)
    uid = db_user(client).id
    with client.app.state.session_factory() as first, client.app.state.session_factory() as second:
        assert totp.consume_recovery_code(first, uid, codes[0]) is True
        assert totp.consume_recovery_code(second, uid, codes[0]) is False  # the other request already took it
        assert totp.consume_recovery_code(second, uid, "aaaa-bbbb-cc") is False
        assert totp.consume_recovery_code(second, uid + 1, codes[1]) is False
        first.commit()


def test_recovery_codes_have_enough_entropy_and_are_unique_per_call():
    codes = {totp.new_recovery_code() for _ in range(200)}
    assert len(codes) == 200 and all(CODE_FORMAT.match(c) for c in codes)
    assert len(totp.RECOVERY_ALPHABET) ** totp.RECOVERY_LENGTH >= 2**50


def test_regenerate_replaces_the_whole_set_and_needs_a_totp_code(account, clock):
    client, session, secret, codes = account
    session = second_step(client, recovery_code=codes[0]).json()
    clock.advance()
    assert regenerate(client, session, codes[1]).status_code == 400  # a recovery code is not accepted here
    response = regenerate(client, session, code_at(secret, clock))
    assert response.status_code == 200
    fresh = response.json()["recovery_codes"]
    assert len(fresh) == 10 and not set(fresh) & set(codes) and len(recovery_rows(client)) == 10
    client.cookies.clear()
    assert second_step(client, recovery_code=codes[2]).status_code == 401
    assert second_step(client, recovery_code=fresh[0]).status_code == 200


def test_regenerate_needs_totp_enabled_and_the_password(client, clock):
    session = register(client)
    assert regenerate(client, session, "123456").status_code == 409
    secret, _ = turn_on(client, session, clock)
    clock.advance()
    assert regenerate(client, session, code_at(secret, clock), {"password": "bad"}).status_code == 403


def test_wrong_codes_on_regenerate_are_throttled(client, clock):
    session = register(client)
    turn_on(client, session, clock)
    statuses = [regenerate(client, session, "000000").status_code for _ in range(6)]
    assert statuses == [400] * 5 + [429]


# --- disable ------------------------------------------------------------------------------------------------


def test_disable_with_a_totp_code_clears_everything_and_revokes_other_sessions(client, clock):
    session = register(client)
    secret, _ = turn_on(client, session, clock)
    other = TestClient(client.app)
    clock.advance()
    other_session = second_step(other, code=code_at(secret, clock)).json()
    assert other.get("/auth/me").status_code == 200
    clock.advance()

    response = disable(client, session, code_at(secret, clock))

    assert response.status_code == 204 and response.content == b""
    user = db_user(client)
    assert (user.totp_enabled, user.totp_secret, user.totp_pending_secret, user.totp_last_step) == (False, None, None, None)
    assert recovery_rows(client) == [] and user.token_version == 2  # enable and disable each bump
    assert other.get("/auth/me").status_code == 401
    me = client.get("/auth/me")  # this session was re-issued
    assert me.status_code == 200 and me.json()["totp_enabled"] is False and me.json()["recovery_codes_left"] == 0
    assert other_session["username"] == "Alice"
    assert client.post("/auth/login", json=CREDS).json().get("mfa_required") is None


def test_disable_with_a_recovery_code(client, clock):
    session = register(client)
    _, codes = turn_on(client, session, clock)
    assert disable(client, session, codes[3]).status_code == 204
    assert db_user(client).totp_enabled is False and recovery_rows(client) == []


def test_disable_rejects_wrong_codes_and_replays(client, clock):
    session = register(client)
    secret, _ = turn_on(client, session, clock)
    assert disable(client, session, code_at(secret, clock)).status_code == 400  # same step as enable: replay
    wrong = disable(client, session, "000000")
    assert (wrong.status_code, wrong.json()) == (400, GENERIC)
    assert disable(client, session, "aaaa-bbbb-cc").status_code == 400
    assert db_user(client).totp_enabled is True and len(recovery_rows(client)) == 10


def test_disable_needs_password_csrf_and_enabled_totp(client, clock):
    session = register(client)
    assert disable(client, session, "123456").status_code == 409
    secret, _ = turn_on(client, session, clock)
    clock.advance()
    code = code_at(secret, clock)
    assert disable(client, session, code, {"password": "bad"}).status_code == 403
    assert client.request("DELETE", "/auth/totp", json={"code": code, **PW}).status_code == 403
    assert db_user(client).totp_enabled is True


def test_wrong_codes_on_disable_are_throttled(client, clock):
    session = register(client)
    turn_on(client, session, clock)
    statuses = [disable(client, session, "000000").status_code for _ in range(6)]
    assert statuses == [400] * 5 + [429]


def test_totp_is_not_a_sign_in_method(client, clock):
    session, auth, _ = passkey_only(client)
    grant_fresh(client)
    secret, _ = turn_on(client, session, clock)  # a passkey-only account has no password to give
    client.cookies.clear()
    from tests.center.test_passkeys import delete, sign_in

    assert sign_in(client, auth).status_code == 200
    grant_fresh(client)
    passkey_id = client.get("/auth/me/passkeys").json()["passkeys"][0]["id"]
    refreshed = client.get("/auth/me").json()
    response = delete(client, f"/auth/me/passkeys/{passkey_id}", refreshed)
    assert response.status_code == 409 and response.json() == {"detail": "Keep at least one sign-in method"}


def test_deleting_the_account_removes_recovery_codes(client, clock):
    session = register(client)
    turn_on(client, session, clock)
    assert client.request("DELETE", "/auth/me", json=PW, headers=csrf(session)).status_code == 204
    assert recovery_rows(client) == []
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RecoveryCode)) == 0


# --- biometrics next to TOTP -----------------------------------------------------------------------------------


@pytest.fixture
def both(bio_client, clock):
    """Alice with voice + face + biometric 2FA and TOTP, signed out. (client, secret)."""
    session = register(bio_client)
    assert enroll(bio_client, session).status_code == 200
    assert set_2fa(bio_client, session).status_code == 200
    secret, _ = turn_on(bio_client, session, clock)
    bio_client.cookies.clear()
    return bio_client, secret


def test_totp_is_the_only_factor_even_with_biometric_2fa_on(both, clock):
    client, secret = both
    body = challenge(client)
    assert body["factors"] == ["totp"]  # a spoofable biometric never substitutes for TOTP

    by_biometric = client.post("/auth/login/biometric", data={"mfa_token": body["mfa_token"]}, files=files(VOICE, FACE))
    assert (by_biometric.status_code, by_biometric.cookies.get("sn_token")) == (401, None)
    clock.advance()
    assert second_step(client, mfa_token=body["mfa_token"], code=code_at(secret, clock)).status_code == 200


def test_biometrics_off_still_totp_only(both, clock):
    client, secret = both
    client.app.state.biometrics = None
    body = challenge(client)
    assert body["factors"] == ["totp"]
    clock.advance()
    assert second_step(client, mfa_token=body["mfa_token"], code=code_at(secret, clock)).status_code == 200


def test_biometric_only_account_still_fails_closed_when_biometrics_are_off(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    set_2fa(bio_client, session)
    bio_client.cookies.clear()
    bio_client.app.state.biometrics = None
    assert bio_client.post("/auth/login", json=CREDS).status_code == 503


def test_biometric_only_account_lists_only_biometric(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    set_2fa(bio_client, session)
    bio_client.cookies.clear()
    assert challenge(bio_client)["factors"] == ["biometric"]


def test_a_totp_only_account_cannot_pass_the_biometric_step(bio_client, clock):
    session = register(bio_client)
    turn_on(bio_client, session, clock)
    bio_client.cookies.clear()
    token = challenge(bio_client)["mfa_token"]
    response = bio_client.post("/auth/login/biometric", data={"mfa_token": token})
    assert response.status_code == 401 and bio_client.get("/auth/me").status_code == 401


def test_biometric_step_is_refused_after_2fa_is_switched_off_meanwhile(both):
    client, _ = both
    token = challenge(client)["mfa_token"]
    set_user(client, biometric_2fa=False)
    response = client.post("/auth/login/biometric", data={"mfa_token": token}, files=files(VOICE, FACE))
    assert response.status_code == 401


# --- notifications ------------------------------------------------------------------------------------------------


def subjects(client, address="alice@example.com"):
    return [m.subject for m in client.app.state.mailer.to(address)]


def test_enable_and_regenerate_send_mail_but_a_failed_recovery_login_does_not(mail_client, clock):
    session = verified_account(mail_client)
    secret, _ = turn_on(mail_client, session, clock)
    assert "Đã bật xác thực hai bước" in last_mail(mail_client, "alice@example.com").subject
    clock.advance()
    assert regenerate(mail_client, session, code_at(secret, clock)).status_code == 200
    assert "Đã tạo lại mã khôi phục" in last_mail(mail_client, "alice@example.com").subject
    mail_client.app.state.mailer.sent.clear()
    mail_client.cookies.clear()
    assert second_step(mail_client, recovery_code="aaaa-bbbb-cc").status_code == 401
    assert subjects(mail_client) == []


def test_recovery_use_and_disable_send_mail(mail_client, clock):
    session = verified_account(mail_client)
    secret, codes = turn_on(mail_client, session, clock)
    mail_client.app.state.mailer.sent.clear()
    mail_client.cookies.clear()
    login = second_step(mail_client, recovery_code=codes[0])
    assert login.status_code == 200
    assert len(subjects(mail_client)) == 1 and "mã khôi phục" in subjects(mail_client)[0]
    clock.advance()
    assert disable(mail_client, login.json(), code_at(secret, clock)).status_code == 204
    assert "Đã tắt xác thực hai bước" in subjects(mail_client)[-1]
    assert codes[0] not in last_mail(mail_client, "alice@example.com").text


def test_no_mail_without_a_verified_address(mail_client, clock):
    session = register(mail_client)
    turn_on(mail_client, session, clock)
    assert mail_client.app.state.mailer.sent == []


# --- passkey cap --------------------------------------------------------------------------------------------------


def link_many(client, session, count):
    for _ in range(count):
        assert link(client, session)[2].status_code == 200


def test_the_eleventh_passkey_is_refused_in_options_and_in_add(client):
    session = register(client)
    link_many(client, session, 9)
    auth = SoftAuthenticator()
    from tests.center.test_passkeys import add, link_options

    pending = link_options(client, session).json()  # still room: the tenth
    credential = auth.create(pending["options"])
    assert add(client, session, credential, pending["challenge_token"]).status_code == 200

    options = link_options(client, session)
    assert (options.status_code, options.json()) == (409, {"detail": "Passkey limit reached"})
    late = add(client, session, SoftAuthenticator().create(pending["options"]), pending["challenge_token"])
    assert late.status_code in (400, 409)
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Passkey)) == 10


def test_add_checks_the_cap_itself_when_options_were_issued_earlier(client):
    from tests.center.test_passkeys import add, link_options

    session = register(client)
    link_many(client, session, 9)
    first = link_options(client, session).json()
    second = link_options(client, session).json()  # two ceremonies started with 9 passkeys
    assert add(client, session, SoftAuthenticator().create(first["options"]), first["challenge_token"]).status_code == 200
    response = add(client, session, SoftAuthenticator().create(second["options"]), second["challenge_token"])
    assert (response.status_code, response.json()) == (409, {"detail": "Passkey limit reached"})


def test_removing_a_passkey_frees_a_slot(client):
    from tests.center.test_passkeys import delete

    session = register(client)
    link_many(client, session, 10)
    first_id = client.get("/auth/me/passkeys").json()["passkeys"][0]["id"]
    assert delete(client, f"/auth/me/passkeys/{first_id}", session, PW).status_code == 200
    assert link(client, session)[2].status_code == 200


# --- migration ---------------------------------------------------------------------------------------------------------


def test_old_database_gets_totp_columns_and_table_and_works(tmp_path, monkeypatch, clock):
    url = make_old_db(tmp_path / "old.db")
    with TestClient(create_app(url)) as client:
        login = client.post("/auth/login", json={"username": "olduser", "password": "legacy-pass-1"})
        assert login.status_code == 200 and login.json()["username"] == "olduser"
        session = login.json()
        user = user_row(client, "olduser")
        assert (user.totp_enabled, user.totp_secret, user.totp_pending_secret, user.totp_last_step) == (False, None, None, None)
        body = {"password": "legacy-pass-1"}
        secret = setup(client, session, body).json()["secret"]
        response = enable(client, session, code_at(secret, clock), body)
        assert response.status_code == 200 and len(response.json()["recovery_codes"]) == 10
        assert client.get("/auth/me").json()["totp_enabled"] is True
    # a second start on the upgraded database is a no-op
    with TestClient(create_app(url)) as again:
        assert again.post("/auth/login", json={"username": "olduser", "password": "legacy-pass-1"}).json()["factors"] == ["totp"]


def test_methods_status_reports_totp_fields(client, clock):
    session = register(client)
    assert client.get("/auth/me").json()["totp_enabled"] is False
    turn_on(client, session, clock)
    body = client.get("/auth/me").json()
    assert body["totp_enabled"] is True and body["recovery_codes_left"] == 10 and body["has_password"] is True


# --- voice / webcam sign-in is a primary factor: TOTP still applies ---------------------------------------------


def _enable_without_password(client, session, clock):
    secret = setup(client, session, {}).json()["secret"]
    response = enable(client, session, code_at(secret, clock), {})
    assert response.status_code == 200
    client.cookies.clear()
    return secret


def _assert_challenge_then_totp(client, response, secret, clock, username):
    body = response.json()
    assert response.status_code == 200 and body["mfa_required"] is True and body["factors"] == ["totp"]
    assert "set-cookie" not in response.headers and client.get("/auth/me").status_code == 401
    clock.advance()
    done = client.post("/auth/login/totp", json={"mfa_token": body["mfa_token"], "code": code_at(secret, clock)})
    assert done.status_code == 200 and done.json()["username"] == username
    client.cookies.clear()


def test_voice_and_webcam_login_with_username_owe_totp(bio_client, clock):
    from tests.center.test_signin_methods import login_voice, login_webcam, reg_voice, reg_webcam

    secrets_ = {}
    for name, reg in (("vera", reg_voice), ("cam", reg_webcam)):
        session = reg(bio_client, name).json()
        secrets_[name] = _enable_without_password(bio_client, session, clock)
    _assert_challenge_then_totp(bio_client, login_voice(bio_client, "vera"), secrets_["vera"], clock, "vera")
    _assert_challenge_then_totp(bio_client, login_webcam(bio_client, "cam"), secrets_["cam"], clock, "cam")


def test_voice_and_webcam_identify_owe_totp(bio_client, clock):
    from tests.center.test_signin_methods import reg_voice, reg_webcam

    audio, video = ("a.webm", b"ana-voice-sample"), ("c.webm", b"f0.00-cam")
    voice_session = reg_voice(bio_client, "vera", audio).json()
    voice_secret = _enable_without_password(bio_client, voice_session, clock)
    _assert_challenge_then_totp(
        bio_client, bio_client.post("/auth/login/voice", files={"audio": audio}), voice_secret, clock, "vera"
    )
    cam_session = reg_webcam(bio_client, "cam", video).json()
    cam_secret = _enable_without_password(bio_client, cam_session, clock)
    _assert_challenge_then_totp(
        bio_client, bio_client.post("/auth/login/webcam", files={"video": video}), cam_secret, clock, "cam"
    )


def test_voice_login_without_totp_is_unchanged(bio_client):
    from tests.center.test_signin_methods import login_voice, reg_voice

    reg_voice(bio_client)
    bio_client.cookies.clear()
    response = login_voice(bio_client, "vera")
    assert "mfa_required" not in response.json() and bio_client.get("/auth/me").status_code == 200


# --- enrolment revokes sessions; secret handling -----------------------------------------------------------------------


def test_enable_bumps_the_token_version_reissues_the_session_and_returns_csrf(client, clock):
    session = register(client)
    thief = TestClient(client.app)
    thief.cookies.update(client.cookies)
    secret = setup(client, session).json()["secret"]
    old_csrf = session["csrf_token"]

    response = enable(client, session, code_at(secret, clock))

    body = response.json()
    assert db_user(client).token_version == 1 and thief.get("/auth/me").status_code == 401
    assert client.get("/auth/me").json()["csrf_token"] == body["csrf_token"] != old_csrf
    assert regenerate(client, session, "000000").status_code == 400  # new csrf is accepted


def test_unseal_failure_is_logged_without_secrets(caplog):
    caplog.set_level(logging.WARNING, logger="auth.audit")
    one = totp.make_cipher(Settings(jwt_secret="a" * 40, data_key=Fernet.generate_key().decode()))
    other = totp.make_cipher(Settings(jwt_secret="a" * 40, data_key=Fernet.generate_key().decode()))
    token = totp.seal(one, "SECRETVALUE")
    assert totp.unseal(other, token) is None
    assert "TOTP secret could not be decrypted" in caplog.text and "SECRETVALUE" not in caplog.text and token not in caplog.text
    assert totp.unseal(other, None) is None


def test_startup_notes_the_derived_key(caplog):
    caplog.set_level(logging.INFO, logger="auth.audit")
    totp.make_cipher(Settings(jwt_secret="a" * 40))
    assert "derived from JWT_SECRET" in caplog.text
