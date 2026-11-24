"""Step-up re-authentication: the `sn_fresh` cookie and who needs it."""

import time

import pytest
from fastapi.testclient import TestClient

from api.center.models import VerificationCode
from api.center.tokens import create_fresh_token
from sn_shared import COOKIE_NAME, create_token, decode_token
from tests.center.fakes import fake_google_verifier
from tests.center.helpers import CREDS, STRONG, cookie_value, csrf, forge, grant_fresh, register, set_cookies
from tests.center.mail_helpers import age_tokens, code_of, last_mail, sent_to, set_user, token_rows, user_row
from tests.center.test_passkeys import link, passkey_only
from tests.center.webauthn_helper import UP, SoftAuthenticator

NEED = {"detail": "Re-authentication required"}
FAILED = {"detail": "Re-authentication failed"}
GINA = "g1|gina@example.com"
GINA_MAIL = "gina@example.com"
SENSITIVE = ("POST", "/auth/totp/setup")  # any ensure_reauth call site will do


def sensitive(client, session, body=None):
    return client.request(SENSITIVE[0], SENSITIVE[1], json={} if body is None else body, headers=csrf(session))


def adopt(client, response) -> None:
    """What the browser does with Set-Cookie: sn_fresh (its path is /api/center/auth; the test jar gets "/")."""
    client.cookies.set("sn_fresh", cookie_value(response, "sn_fresh"), path="/")


def passkey_proof(client, session, auth, handle, **get):
    options = client.post("/auth/reauth/passkey/options", headers=csrf(session))
    assert options.status_code == 200, options.text
    data = options.json()
    credential = auth.get(data["options"], user_handle=handle, **get)
    return client.post(
        "/auth/reauth/passkey/verify", json={"credential": credential, "challenge_token": data["challenge_token"]},
        headers=csrf(session),
    )  # fmt: skip


def google_account(client, token=GINA):
    session = client.post("/auth/google", json={"id_token": token}).json()
    return session


def email_proof(client, session, address=GINA_MAIL):
    assert client.post("/auth/reauth/email/request", headers=csrf(session)).status_code == 202
    code = code_of(last_mail(client, address))
    return client.post("/auth/reauth/email/verify", json={"code": code}, headers=csrf(session))


# --- who needs a proof ----------------------------------------------------------------------------------


def test_a_passwordless_account_without_a_proof_gets_the_exact_401_shape(client):
    session, _, _ = passkey_only(client)
    response = sensitive(client, session)
    assert response.status_code == 401
    assert response.json() == {**NEED, "reauth": ["passkey"]}
    assert "sn_fresh" not in set_cookies(response)


def test_every_call_site_is_guarded(google_client):
    client = google_client
    session = google_account(client)
    calls = [
        ("POST", "/auth/me/password", {"new_password": STRONG}),
        ("POST", "/auth/me/google", {"id_token": "g2|other@example.com"}),
        ("DELETE", "/auth/me/google", None),
        ("DELETE", "/auth/me", None),
        ("POST", "/auth/totp/setup", {}),
        ("POST", "/auth/totp/enable", {"code": "000000"}),
        ("DELETE", "/auth/totp", {"code": "000000"}),
        ("POST", "/auth/totp/recovery-codes", {"code": "000000"}),
        ("POST", "/auth/me/passkeys/options", {}),
    ]
    for method, url, body in calls:
        response = client.request(method, url, json=body, headers=csrf(session))
        assert response.status_code == 401 and response.json()["reauth"] == ["google"], (url, response.text)


def test_a_valid_proof_unlocks_the_sensitive_call(client):
    session, auth, handle = passkey_only(client)
    proof = passkey_proof(client, session, auth, handle)
    assert proof.status_code == 200
    adopt(client, proof)
    assert sensitive(client, session).status_code == 200


def test_password_accounts_are_unchanged(client):
    session = register(client)
    assert sensitive(client, session, {}).status_code == 403  # no password: same 403 as before
    assert sensitive(client, session, {"password": "wrong-password"}).json() == {"detail": "Incorrect password"}
    assert sensitive(client, session, {"password": CREDS["password"]}).status_code == 200


def test_a_password_account_also_accepts_a_fresh_proof(client):
    session = register(client)
    grant_fresh(client)
    assert sensitive(client, session, {}).status_code == 200


def test_an_account_with_no_way_to_prove_itself_is_let_through(bio_client):
    session = bio_client.post(
        "/auth/register/voice", data={"username": "vera"}, files={"audio": ("v.webm", b"vera-voice-sample")}
    ).json()
    assert bio_client.get("/auth/reauth/methods").json() == {"methods": []}
    assert sensitive(bio_client, session).status_code == 200


# --- methods ----------------------------------------------------------------------------------------------


def test_methods_list_what_the_user_can_use(mail_client):
    session = register(mail_client)
    assert mail_client.get("/auth/reauth/methods").json() == {"methods": ["password"]}
    link(mail_client, session)
    set_user(mail_client, email="alice@example.com", email_verified=True)
    set_user(mail_client, google_sub="g-1")
    assert mail_client.get("/auth/reauth/methods").json() == {"methods": ["password", "passkey", "google", "email"]}
    set_user(mail_client, email_verified=False)
    assert mail_client.get("/auth/reauth/methods").json() == {"methods": ["password", "passkey", "google"]}


def test_methods_leave_out_what_the_server_cannot_do(client):
    register(client)
    set_user(client, google_sub="g-1", email="alice@example.com", email_verified=True)
    assert client.get("/auth/reauth/methods").json() == {"methods": ["password"]}  # no Google verifier, no SMTP


def test_methods_need_a_login(client):
    assert client.get("/auth/reauth/methods").status_code == 401


# --- passkey ----------------------------------------------------------------------------------------------


def test_passkey_proof_sets_a_correct_cookie_and_returns_fresh_until(client):
    session, auth, handle = passkey_only(client)
    before = time.time()
    response = passkey_proof(client, session, auth, handle)
    assert response.status_code == 200 and set(response.json()) == {"fresh_until"}
    line = set_cookies(response)["sn_fresh"]
    assert "Path=/api/center/auth" in line and "HttpOnly" in line and "SameSite=lax" in line and "Max-Age=300" in line
    assert "Secure" not in line
    claims = __import__("api.center.tokens", fromlist=["x"]).decode_claims(cookie_value(response, "sn_fresh"), "fresh")
    assert claims["sub"] == str(session["id"]) and claims["sid"] == decode_token(client.cookies.get(COOKIE_NAME)).sid
    assert 295 <= claims["exp"] - before <= 305


def test_the_fresh_cookie_is_secure_when_the_settings_say_so(monkeypatch):
    from api.center.main import create_app

    monkeypatch.setenv("COOKIE_SECURE", "1")
    with TestClient(create_app("sqlite://"), base_url="https://testserver") as secure:
        session, auth, handle = passkey_only(secure)
        assert "Secure" in set_cookies(passkey_proof(secure, session, auth, handle))["sn_fresh"]


def test_another_users_passkey_is_refused(client):
    session, _, _ = passkey_only(client, "alice")
    bob = TestClient(client.app)
    _, bob_auth, bob_handle = passkey_only(bob, "bob")
    options = client.post("/auth/reauth/passkey/options", headers=csrf(session)).json()
    credential = bob_auth.get(options["options"], user_handle=bob_handle)  # a real, valid assertion... of Bob's
    response = client.post(
        "/auth/reauth/passkey/verify",
        json={"credential": credential, "challenge_token": options["challenge_token"]}, headers=csrf(session),
    )  # fmt: skip
    assert response.status_code == 401 and response.json() == FAILED and "sn_fresh" not in set_cookies(response)


def test_a_challenge_minted_for_someone_else_is_refused(client):
    alice, auth, handle = passkey_only(client, "alice")
    bob = TestClient(client.app)
    bob_session, _, _ = passkey_only(bob, "bob")
    options = bob.post("/auth/reauth/passkey/options", headers=csrf(bob_session)).json()
    credential = auth.get(options["options"], user_handle=handle)
    response = client.post(
        "/auth/reauth/passkey/verify",
        json={"credential": credential, "challenge_token": options["challenge_token"]}, headers=csrf(alice),
    )  # fmt: skip
    assert response.status_code == 401 and response.json() == FAILED


def test_passkey_proof_is_single_use_and_demands_user_verification(client):
    session, auth, handle = passkey_only(client)
    options = client.post("/auth/reauth/passkey/options", headers=csrf(session)).json()
    body = {"credential": auth.get(options["options"], user_handle=handle), "challenge_token": options["challenge_token"]}
    assert client.post("/auth/reauth/passkey/verify", json=body, headers=csrf(session)).status_code == 200
    replay = client.post("/auth/reauth/passkey/verify", json=body, headers=csrf(session))
    assert replay.status_code == 401 and replay.json() == FAILED

    no_uv = passkey_proof(client, session, auth, handle, flags=UP)
    assert no_uv.status_code == 401 and no_uv.json() == FAILED


def test_passkey_login_challenges_do_not_work_here_and_vice_versa(client):
    session, auth, handle = passkey_only(client)
    login = client.post("/auth/passkey/options").json()
    response = client.post(
        "/auth/reauth/passkey/verify",
        json={"credential": auth.get(login["options"], user_handle=handle), "challenge_token": login["challenge_token"]},
        headers=csrf(session),
    )  # fmt: skip
    assert response.status_code == 401
    options = client.post("/auth/reauth/passkey/options", headers=csrf(session)).json()
    client.cookies.clear()
    stolen = client.post(
        "/auth/passkey/login",
        json={"credential": auth.get(options["options"], user_handle=handle), "challenge_token": options["challenge_token"]},
    )  # fmt: skip
    assert stolen.status_code == 401  # a reauth challenge never signs anybody in


def test_passkey_reauth_rejects_garbage_and_a_regressed_counter(client):
    session, auth, handle = passkey_only(client)
    garbage = client.post(
        "/auth/reauth/passkey/verify", json={"credential": {}, "challenge_token": "x"}, headers=csrf(session)
    )
    assert garbage.status_code == 401
    assert passkey_proof(client, session, auth, handle).status_code == 200
    assert passkey_proof(client, session, auth, handle, counter=1).status_code == 401  # not above the stored one


def test_passkey_reauth_is_throttled_per_user(client):
    session, auth, handle = passkey_only(client)
    for _ in range(5):
        assert passkey_proof(client, session, auth, handle, flags=UP).status_code == 401
    assert passkey_proof(client, session, auth, handle).status_code == 429
    assert client.post("/auth/reauth/passkey/verify", json={"credential": {}, "challenge_token": "x"},
                       headers=csrf(session)).status_code == 429  # fmt: skip


def test_reauth_writes_need_csrf_and_a_login(client):
    session, _, _ = passkey_only(client)
    for url, body in (
        ("/auth/reauth/passkey/options", None), ("/auth/reauth/passkey/verify", {"credential": {}, "challenge_token": "x"}),
        ("/auth/reauth/google", {"id_token": "x"}),
    ):  # fmt: skip
        assert client.post(url, json=body).status_code == 403, url
        assert client.post(url, json=body, headers={**csrf(session), "Origin": "https://evil.example"}).status_code == 403
    client.cookies.clear()
    assert client.post("/auth/reauth/passkey/options", headers=csrf(session)).status_code == 401


# --- Google -------------------------------------------------------------------------------------------------


def test_google_proof(google_client):
    client = google_client
    session = google_account(client)
    assert client.get("/auth/reauth/methods").json() == {"methods": ["google"]}
    response = client.post("/auth/reauth/google", json={"id_token": GINA}, headers=csrf(session))
    assert response.status_code == 200 and "fresh_until" in response.json()
    adopt(client, response)
    assert sensitive(client, session).status_code == 200


def test_google_proof_failures_are_generic(google_client):
    client = google_client
    session = google_account(client)
    for token in ("bad-token", "g2|gina@example.com", "g1x|gina@example.com"):  # rejected, another sub, another sub
        response = client.post("/auth/reauth/google", json={"id_token": token}, headers=csrf(session))
        assert response.status_code == 401 and response.json() == FAILED, token
    assert "sn_fresh" not in set_cookies(response)


def test_google_proof_for_an_account_without_google_and_when_unconfigured(client):
    session = register(client)
    assert client.post("/auth/reauth/google", json={"id_token": "x"}, headers=csrf(session)).status_code == 503
    client.app.state.google_verifier = fake_google_verifier
    other = TestClient(client.app)
    session = other.post("/auth/register", json={"username": "bob", "password": STRONG}).json()
    response = other.post("/auth/reauth/google", json={"id_token": GINA}, headers=csrf(session))
    assert response.status_code == 401 and response.json() == FAILED  # a real Google token, but not linked to Bob


def test_google_proof_is_throttled(google_client):
    client = google_client
    session = google_account(client)
    for _ in range(5):
        client.post("/auth/reauth/google", json={"id_token": "g2|x@example.com"}, headers=csrf(session))
    assert client.post("/auth/reauth/google", json={"id_token": GINA}, headers=csrf(session)).status_code == 429


# --- mailed code --------------------------------------------------------------------------------------------


def test_email_proof_end_to_end(mail_client):
    client = mail_client
    session = google_account(client)
    assert client.get("/auth/reauth/methods").json() == {"methods": ["google", "email"]}

    assert client.post("/auth/reauth/email/request", headers=csrf(session)).status_code == 202
    (message,) = sent_to(client, GINA_MAIL)
    assert code_of(message).isdigit() and len(code_of(message)) == 6
    assert "http" not in message.text and "#token" not in message.text and "http" not in message.html  # code only
    row = token_rows(client)[-1]
    assert (row.purpose, row.target) == ("reauth", GINA_MAIL)
    assert 9 * 60 < (row.expires_at.replace(tzinfo=None) - __import__("datetime").datetime.utcnow()).total_seconds() <= 600

    response = client.post("/auth/reauth/email/verify", json={"code": code_of(message)}, headers=csrf(session))
    assert response.status_code == 200 and "fresh_until" in response.json()
    adopt(client, response)
    assert sensitive(client, session).status_code == 200


def test_the_email_code_is_single_use_and_wrong_or_expired_codes_fail_generically(mail_client):
    client = mail_client
    session = google_account(client)
    client.post("/auth/reauth/email/request", headers=csrf(session))
    code = code_of(last_mail(client, GINA_MAIL))
    wrong = "000000" if code != "000000" else "111111"
    bad = client.post("/auth/reauth/email/verify", json={"code": wrong}, headers=csrf(session))
    assert bad.status_code == 401 and bad.json() == FAILED
    assert client.post("/auth/reauth/email/verify", json={"code": code}, headers=csrf(session)).status_code == 200
    again = client.post("/auth/reauth/email/verify", json={"code": code}, headers=csrf(session))
    assert again.status_code == 401 and again.json() == FAILED

    client.post("/auth/reauth/email/request", headers=csrf(session))
    code = code_of(last_mail(client, GINA_MAIL))
    age_tokens(client, minutes=11)
    assert client.post("/auth/reauth/email/verify", json={"code": code}, headers=csrf(session)).status_code == 401


def test_a_login_code_is_not_a_reauth_code(mail_client):
    client = mail_client
    session = google_account(client)
    client.cookies.clear()
    client.post("/auth/email/login/request", json={"email": GINA_MAIL})
    login_code = code_of(last_mail(client, GINA_MAIL))
    done = client.post("/auth/email/login/verify", json={"email": GINA_MAIL, "code": login_code})
    assert done.status_code == 200
    response = client.post("/auth/reauth/email/verify", json={"code": login_code}, headers=csrf(done.json()))
    assert response.status_code == 401
    assert session["id"] == done.json()["id"]


def test_the_code_goes_only_to_a_verified_address_of_the_account(mail_client):
    client = mail_client
    session = register(client)
    grant = client.post("/auth/reauth/email/request", headers=csrf(session))
    assert grant.status_code == 202 and client.app.state.mailer.sent == []  # no email: same 202, nothing sent
    set_user(client, email="alice@example.com", email_verified=False)
    assert client.post("/auth/reauth/email/request", headers=csrf(session)).status_code == 202
    assert client.app.state.mailer.sent == []  # unverified: nothing
    assert client.post("/auth/reauth/email/verify", json={"code": "123456"}, headers=csrf(session)).status_code == 401
    assert [r for r in token_rows(client) if r.purpose == "reauth"] == []


def test_a_code_mailed_before_the_address_was_removed_is_dead(mail_client):
    client = mail_client
    session = google_account(client)
    client.post("/auth/reauth/email/request", headers=csrf(session))
    code = code_of(last_mail(client, GINA_MAIL))
    set_user(client, "gina", email=None, email_verified=False)
    assert client.post("/auth/reauth/email/verify", json={"code": code}, headers=csrf(session)).status_code == 401


def test_email_requests_are_budgeted_and_wrong_codes_throttled(mail_client):
    client = mail_client
    session = google_account(client)
    statuses = [client.post("/auth/reauth/email/request", headers=csrf(session)).status_code for _ in range(4)]
    assert statuses == [202, 202, 202, 429]  # 3 per (address, mailbox) per window, like login mail
    codes = [
        client.post("/auth/reauth/email/verify", json={"code": "000000"}, headers=csrf(session)).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_email_proof_is_unavailable_without_mail(client):
    session = register(client)
    assert client.post("/auth/reauth/email/request", headers=csrf(session)).status_code == 503
    assert client.post("/auth/reauth/email/verify", json={"code": "123456"}, headers=csrf(session)).status_code == 503


# --- the cookie is bound to user, session, version and time ---------------------------------------------------


def test_a_proof_from_another_session_does_not_work(client):
    session, auth, handle = passkey_only(client)
    proof = passkey_proof(client, session, auth, handle)
    other = TestClient(client.app)
    from tests.center.test_passkeys import sign_in

    assert sign_in(other, auth).status_code == 200
    other.cookies.set("sn_fresh", cookie_value(proof, "sn_fresh"), path="/")  # Alice's proof, a different device
    response = sensitive(other, other.get("/auth/me").json())
    assert response.status_code == 401 and response.json()["reauth"] == ["passkey"]


def test_a_proof_for_another_user_does_not_work(client):
    alice, _, _ = passkey_only(client, "alice")
    bob = TestClient(client.app)
    bob_session, bob_auth, bob_handle = passkey_only(bob, "bob")
    bob_proof = passkey_proof(bob, bob_session, bob_auth, bob_handle)
    client.cookies.set("sn_fresh", cookie_value(bob_proof, "sn_fresh"), path="/")
    assert sensitive(client, alice).status_code == 401


def test_expired_forged_and_stale_version_proofs_do_not_work(client):
    session, _, _ = passkey_only(client)
    payload = decode_token(client.cookies.get(COOKIE_NAME))
    uid, sid = payload.user_id, payload.sid
    bad = {
        "expired": forge({"sub": str(uid), "typ": "fresh", "ver": 0, "sid": sid, "exp": int(time.time()) - 5}),
        "wrong secret": forge({"sub": str(uid), "typ": "fresh", "ver": 0, "sid": sid}, secret="z" * 40),
        "wrong kind": forge({"sub": str(uid), "typ": "refresh", "ver": 0, "sid": sid}),
        "old version": create_fresh_token(uid, 99, 300, sid),
        "no sid on a sid session": create_fresh_token(uid, 0, 300, None),
        "another sid": create_fresh_token(uid, 0, 300, "e" * 32),
        "garbage": "not-a-jwt",
    }
    for name, token in bad.items():
        client.cookies.set("sn_fresh", token, path="/")
        assert sensitive(client, session).status_code == 401, name
    client.cookies.set("sn_fresh", create_fresh_token(uid, 0, 300, sid), path="/")
    assert sensitive(client, session).status_code == 200


def test_a_legacy_session_accepts_only_a_proof_without_a_sid(client):
    session, _, _ = passkey_only(client)
    uid = decode_token(client.cookies.get(COOKIE_NAME)).user_id
    legacy = create_token(uid, session["username"], ver=0)  # no sid: issued before sessions existed
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, legacy, path="/")
    headers = {"X-CSRF-Token": __import__("api.center.tokens", fromlist=["x"]).csrf_token(legacy)}
    client.cookies.set("sn_fresh", create_fresh_token(uid, 0, 300, "d" * 32), path="/")
    assert client.post("/auth/totp/setup", json={}, headers=headers).status_code == 401
    client.cookies.set("sn_fresh", create_fresh_token(uid, 0, 300, None), path="/")
    assert client.post("/auth/totp/setup", json={}, headers=headers).status_code == 200


def test_the_proof_dies_with_the_version(client):
    session, _, _ = passkey_only(client)
    grant_fresh(client)
    assert sensitive(client, session).status_code == 200  # set TOTP up (does not bump)
    user_version = user_row(client, session["username"]).token_version
    assert user_version == 0
    from api.center.tokenversion import bump_token_version

    with client.app.state.session_factory() as db:
        from api.center.models import User

        bump_token_version(db, db.get(User, session["id"]))
        db.commit()
    assert client.get("/auth/me").status_code == 401  # the whole session died, so the proof cannot be used either


def test_logout_clears_the_fresh_cookie(client):
    session, auth, handle = passkey_only(client)
    adopt(client, passkey_proof(client, session, auth, handle))
    response = client.post("/auth/logout", headers=csrf(session))
    assert response.status_code == 204 and "Max-Age=0" in set_cookies(response)["sn_fresh"]
    assert "Path=/api/center/auth" in set_cookies(response)["sn_fresh"]


def test_email_rows_of_the_reauth_purpose_are_kept_small(mail_client):
    client = mail_client
    session = google_account(client)
    for _ in range(3):
        client.post("/auth/reauth/email/request", headers=csrf(session))
    rows = [r for r in token_rows(client) if r.purpose == "reauth"]
    assert len(rows) == 3 and all(isinstance(r, VerificationCode) for r in rows)
    assert [m.subject for m in sent_to(client, GINA_MAIL)][0].startswith("Xác nhận thao tác")


def test_a_passkey_can_be_linked_after_a_proof(google_client):
    client = google_client
    session = google_account(client)
    assert client.post("/auth/me/passkeys/options", json={}, headers=csrf(session)).status_code == 401
    grant_fresh(client)
    auth, _, added = link(client, session, auth=SoftAuthenticator(), body={})
    assert added.status_code == 200
    assert client.get("/auth/reauth/methods").json() == {"methods": ["passkey", "google"]}


def test_a_google_id_token_buys_only_one_proof(google_client):
    client = google_client
    session = google_account(client)
    first = client.post("/auth/reauth/google", json={"id_token": GINA}, headers=csrf(session))
    again = client.post("/auth/reauth/google", json={"id_token": GINA}, headers=csrf(session))
    assert first.status_code == 200 and again.status_code == 401 and again.json() == FAILED


def test_the_fresh_throttle_is_per_user_and_address(client):
    session, auth, handle = passkey_only(client)
    for _ in range(5):
        assert passkey_proof(client, session, auth, handle, flags=UP).status_code == 401
    assert client.app.state.fresh_throttle.is_blocked(f"{session['id']}|testclient")
    assert not client.app.state.fresh_throttle.is_blocked(f"{session['id']}|198.51.100.7")


def test_a_fresh_token_cannot_be_used_as_a_session(client):
    session, _, _ = passkey_only(client)
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, create_fresh_token(session["id"], 0, 300, None), path="/")
    assert client.get("/auth/me").status_code == 401
