"""Email sign-in (magic link + code), forgot/reset password, anti-enumeration and throttles."""

from fastapi.testclient import TestClient

from api.center import emailtokens as et
from tests.center.helpers import CREDS, STRONG, csrf, refresh_with, register
from tests.center.helpers import cookie_value
from tests.center.mail_helpers import (
    EMAIL, PUBLIC_URL, age_tokens, code_of, last_mail, link_of, sent_to, set_user, token_of, token_rows,
    user_row, verified_account,
)  # fmt: skip

REQUEST = "/auth/email/login/request"
ID_ENDPOINT = "/auth/email/login/verify"
MAGIC = "/auth/email/login/magic"
FORGOT = "/auth/password/forgot"
RESET = "/auth/password/reset"
EXPIRED_CODE = {"detail": "Invalid or expired code"}
EXPIRED_LINK = {"detail": "Invalid or expired link"}


def from_ip(client, address):
    """The same app seen from another client address."""
    return TestClient(client.app, client=(address, 5000))


def ask(client, email=EMAIL):
    return client.post(REQUEST, json={"email": email})


def known_account(client):
    verified_account(client)
    client.cookies.clear()


# --- email sign-in -----------------------------------------------------------------------------


def test_login_request_mails_link_and_code_to_a_verified_account(mail_client):
    known_account(mail_client)
    response = ask(mail_client)
    assert (response.status_code, response.json()) == (202, {"ok": True})
    mail = last_mail(mail_client, EMAIL)
    assert link_of(mail).startswith(f"{PUBLIC_URL}/login/magic#token=")
    assert "?token=" not in link_of(mail) and code_of(mail) not in link_of(mail)


def test_login_with_the_code(mail_client):
    known_account(mail_client)
    ask(mail_client)

    response = mail_client.post(ID_ENDPOINT, json={"email": " Alice@Example.com ", "code": code_of(last_mail(mail_client, EMAIL))})

    assert response.status_code == 200
    assert {"id", "username", "group", "csrf_token"} <= set(response.json())
    assert mail_client.get("/auth/me").json()["username"] == "Alice"
    assert refresh_with(mail_client, cookie_value(response, "sn_refresh")).status_code == 200


def test_login_with_the_magic_link(mail_client):
    known_account(mail_client)
    ask(mail_client)

    response = mail_client.post(MAGIC, json={"token": token_of(last_mail(mail_client, EMAIL))})

    assert response.status_code == 200 and response.json()["username"] == "Alice"
    assert mail_client.get("/auth/me").status_code == 200


def test_a_get_on_the_link_does_not_burn_the_token(mail_client):
    known_account(mail_client)
    ask(mail_client)
    token = token_of(last_mail(mail_client, EMAIL))
    mail_client.get(f"/login/magic?token={token}")
    mail_client.get(f"/auth/email/login/magic?token={token}")
    assert mail_client.post(MAGIC, json={"token": token}).status_code == 200


def test_code_and_link_are_single_use_and_share_one_row(mail_client):
    known_account(mail_client)
    ask(mail_client)
    mail = last_mail(mail_client, EMAIL)
    assert mail_client.post(MAGIC, json={"token": token_of(mail)}).status_code == 200
    again = mail_client.post(MAGIC, json={"token": token_of(mail)})
    assert (again.status_code, again.json()) == (401, EXPIRED_LINK)
    by_code = mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": code_of(mail)})
    assert (by_code.status_code, by_code.json()) == (401, EXPIRED_CODE)


def test_wrong_codes_kill_only_the_code_after_five(mail_client):
    known_account(mail_client)
    ask(mail_client)
    mail = last_mail(mail_client, EMAIL)
    wrong = "000000" if code_of(mail) != "000000" else "111111"
    for _ in range(et.MAX_CODE_ATTEMPTS):
        assert mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": wrong}).json() == EXPIRED_CODE
    assert mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": code_of(mail)}).status_code == 401
    assert mail_client.post(MAGIC, json={"token": token_of(mail)}).status_code == 200  # the link still works


def test_expired_code_and_link(mail_client):
    known_account(mail_client)
    ask(mail_client)
    mail = last_mail(mail_client, EMAIL)
    age_tokens(mail_client, minutes=1)
    assert mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": code_of(mail)}).json() == EXPIRED_CODE
    assert mail_client.post(MAGIC, json={"token": token_of(mail)}).json() == EXPIRED_LINK


def test_login_token_lives_fifteen_minutes(mail_client):
    known_account(mail_client)
    ask(mail_client)
    (row,) = token_rows(mail_client)
    from api.center.models import utcnow

    ttl = (row.expires_at.replace(tzinfo=utcnow().tzinfo) - utcnow()).total_seconds()
    assert 14 * 60 < ttl <= 15 * 60


def test_login_with_a_changed_email_invalidates_old_tokens(mail_client):
    known_account(mail_client)
    ask(mail_client)
    mail = last_mail(mail_client, EMAIL)
    set_user(mail_client, email="moved@example.com")
    assert mail_client.post(MAGIC, json={"token": token_of(mail)}).status_code == 401


def test_unverified_address_gets_no_login_mail(mail_client):
    session = register(mail_client)
    set_user(mail_client, email=EMAIL, email_verified=False)
    mail_client.cookies.clear()
    assert ask(mail_client).status_code == 202
    assert sent_to(mail_client, EMAIL) == []
    assert token_rows(mail_client) == []


def test_unknown_and_known_addresses_look_identical(mail_client):
    known_account(mail_client)
    known = ask(mail_client, EMAIL)
    unknown = ask(mail_client, "nobody@example.com")
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json()) == (202, {"ok": True})
    assert set(known.headers) == set(unknown.headers)
    assert len(sent_to(mail_client, EMAIL)) == 1
    assert sent_to(mail_client, "nobody@example.com") == []
    wrong_known = mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": "000000"})
    wrong_unknown = mail_client.post(ID_ENDPOINT, json={"email": "nobody@example.com", "code": "000000"})
    assert (wrong_known.status_code, wrong_known.json()) == (wrong_unknown.status_code, wrong_unknown.json())


def test_throttle_per_email_is_three_per_window_and_independent_of_the_account(mail_client):
    known_account(mail_client)
    for number, address in enumerate((EMAIL, "ghost@example.com")):
        visitor = from_ip(mail_client, f"203.0.113.{number + 10}")  # the per-IP cap is a separate counter
        codes = [ask(visitor, address).status_code for _ in range(4)]
        assert codes == [202, 202, 202, 429], address
    assert ask(visitor, "ghost@example.com").json() == {"detail": "Too many attempts, try later"}


def test_throttle_per_ip_is_five_per_window(mail_client):
    codes = [ask(mail_client, f"user{i}@example.com").status_code for i in range(6)]
    assert codes == [202] * 5 + [429]


def test_code_submissions_are_throttled_per_ip(mail_client):
    codes = [
        mail_client.post(ID_ENDPOINT, json={"email": f"ghost{i}@example.com", "code": "123456"}).status_code
        for i in range(21)
    ]
    assert codes[:20] == [401] * 20 and codes[20] == 429
    assert mail_client.post(MAGIC, json={"token": "x"}).status_code == 429  # one counter for code/link submissions


def test_email_login_hands_over_to_the_second_factor(mail_bio_client):
    client = mail_bio_client
    known_account(client)
    set_user(client, biometric_2fa=True, audio_embedding=b"x", voice_login=True)
    ask(client)
    mail = last_mail(client, EMAIL)

    by_code = client.post(ID_ENDPOINT, json={"email": EMAIL, "code": code_of(mail)})

    assert by_code.status_code == 200 and by_code.json()["mfa_required"] is True and by_code.json()["mfa_token"]
    assert "set-cookie" not in by_code.headers
    ask(client)
    by_link = client.post(MAGIC, json={"token": token_of(last_mail(client, EMAIL))})
    assert by_link.json()["mfa_required"] is True and client.get("/auth/me").status_code == 401


def test_email_login_fails_closed_when_biometrics_are_off(mail_client):
    known_account(mail_client)
    set_user(mail_client, biometric_2fa=True, audio_embedding=b"x", voice_login=True)
    ask(mail_client)
    response = mail_client.post(MAGIC, json={"token": token_of(last_mail(mail_client, EMAIL))})
    assert response.status_code == 503


def test_email_only_account_can_sign_in(mail_client):
    verified_account(mail_client)
    set_user(mail_client, password_hash="!")
    mail_client.cookies.clear()
    ask(mail_client)
    assert mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": code_of(last_mail(mail_client, EMAIL))}).status_code == 200


def test_links_use_public_url_even_with_a_hostile_host_header(mail_client):
    known_account(mail_client)
    ask_response = mail_client.post(REQUEST, json={"email": EMAIL}, headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"})
    assert ask_response.status_code == 202
    mail_client.post(FORGOT, json={"email": EMAIL}, headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"})
    for mail in sent_to(mail_client, EMAIL):
        assert link_of(mail).startswith(PUBLIC_URL + "/")
        assert "evil" not in mail.text and "evil" not in mail.html


# --- forgot / reset ----------------------------------------------------------------------------


def forgot(client, email=EMAIL):
    return client.post(FORGOT, json={"email": email})


def test_forgot_mails_a_reset_link_only_to_a_verified_account(mail_client):
    known_account(mail_client)
    response = forgot(mail_client)
    assert (response.status_code, response.json()) == (202, {"ok": True})
    mail = last_mail(mail_client, EMAIL)
    assert link_of(mail).startswith(f"{PUBLIC_URL}/reset-password#token=")
    assert "?token=" not in link_of(mail)
    assert (token_rows(mail_client)[0].purpose, token_rows(mail_client)[0].code_hash) == ("reset", None)
    ghost = forgot(mail_client, "ghost@example.com")
    assert (ghost.status_code, ghost.json()) == (202, {"ok": True})
    assert sent_to(mail_client, "ghost@example.com") == [] and len(sent_to(mail_client, EMAIL)) == 1


def test_forgot_throttles_do_not_depend_on_the_account(mail_client):
    known_account(mail_client)
    for number, address in enumerate((EMAIL, "ghost@example.com")):
        visitor = from_ip(mail_client, f"203.0.113.{number + 20}")
        assert [forgot(visitor, address).status_code for _ in range(4)] == [202, 202, 202, 429]


def test_forgot_per_ip_limit(mail_client):
    codes = [forgot(mail_client, f"user{i}@example.com").status_code for i in range(6)]
    assert codes == [202] * 5 + [429]


def test_reset_sets_the_password_and_does_not_sign_in(mail_client):
    known_account(mail_client)
    forgot(mail_client)
    mail = last_mail(mail_client, EMAIL)
    mail_client.app.state.mailer.sent.clear()

    response = mail_client.post(RESET, json={"token": token_of(mail), "new_password": STRONG})

    assert (response.status_code, response.json()) == (200, {"ok": True})
    assert "set-cookie" not in response.headers and mail_client.get("/auth/me").status_code == 401
    assert mail_client.post("/auth/login", json=CREDS).status_code == 401
    assert mail_client.post("/auth/login", json={"username": "alice", "password": STRONG}).status_code == 200
    assert len(sent_to(mail_client, EMAIL)) == 1  # the notification


def test_reset_kills_every_session_and_refresh_token(mail_client):
    session = verified_account(mail_client)
    old_login = mail_client.post("/auth/login", json=CREDS)
    refresh = cookie_value(old_login, "sn_refresh")
    old_version = user_row(mail_client).token_version
    forgot(mail_client)
    mail_client.post(RESET, json={"token": token_of(last_mail(mail_client, EMAIL)), "new_password": STRONG})
    assert user_row(mail_client).token_version == old_version + 1
    mail_client.cookies.clear()
    assert refresh_with(mail_client, refresh).status_code == 401
    assert session["csrf_token"]


def test_reset_enforces_the_password_policy_without_burning_the_token(mail_client):
    known_account(mail_client)
    forgot(mail_client)
    token = token_of(last_mail(mail_client, EMAIL))
    for weak in ("short", "password123", "aaaaaaaaaa", "alice"):
        response = mail_client.post(RESET, json={"token": token, "new_password": weak})
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert mail_client.post(RESET, json={"token": token, "new_password": STRONG}).status_code == 200


def test_reset_token_is_single_use_and_expires(mail_client):
    known_account(mail_client)
    forgot(mail_client)
    token = token_of(last_mail(mail_client, EMAIL))
    assert mail_client.post(RESET, json={"token": token, "new_password": STRONG}).status_code == 200
    again = mail_client.post(RESET, json={"token": token, "new_password": "Another-Strong-1"})
    assert (again.status_code, again.json()) == (400, EXPIRED_LINK)
    forgot_again = mail_client.post(FORGOT, json={"email": EMAIL})
    assert forgot_again.status_code == 202
    token2 = token_of(last_mail(mail_client, EMAIL))
    age_tokens(mail_client, minutes=1)
    assert mail_client.post(RESET, json={"token": token2, "new_password": STRONG}).json() == EXPIRED_LINK
    assert mail_client.post(RESET, json={"token": "garbage", "new_password": STRONG}).json() == EXPIRED_LINK


def test_reset_ttl_is_thirty_minutes(mail_client):
    known_account(mail_client)
    forgot(mail_client)
    from api.center.models import utcnow

    (row,) = token_rows(mail_client)
    ttl = (row.expires_at.replace(tzinfo=utcnow().tzinfo) - utcnow()).total_seconds()
    assert 29 * 60 < ttl <= 30 * 60


def test_reset_is_throttled_per_ip(mail_client):
    codes = [mail_client.post(RESET, json={"token": f"t{i}", "new_password": STRONG}).status_code for i in range(21)]
    assert codes[:20] == [400] * 20 and codes[20] == 429


def test_reset_works_for_an_account_without_a_password(mail_client):
    verified_account(mail_client)
    set_user(mail_client, password_hash="!")
    mail_client.cookies.clear()
    forgot(mail_client)
    assert mail_client.post(RESET, json={"token": token_of(last_mail(mail_client, EMAIL)), "new_password": STRONG}).status_code == 200
    assert mail_client.post("/auth/login", json={"username": "alice", "password": STRONG}).status_code == 200


def test_a_new_forgot_keeps_up_to_three_live_links_and_drops_the_oldest(mail_client):
    known_account(mail_client)
    forgot(mail_client)
    first = token_of(last_mail(mail_client, EMAIL))
    for number in range(et.MAX_LIVE_TOKENS):
        forgot(from_ip(mail_client, f"198.51.100.{number + 1}"))  # one IP may ask only three times per address
    assert len(token_rows(mail_client)) == et.MAX_LIVE_TOKENS
    assert mail_client.post(RESET, json={"token": first, "new_password": STRONG}).status_code == 400
    latest = token_of(last_mail(mail_client, EMAIL))
    assert mail_client.post(RESET, json={"token": latest, "new_password": STRONG}).status_code == 200


def test_a_stranger_cannot_wipe_the_owners_pending_mail(mail_client):
    known_account(mail_client)
    forgot(mail_client)
    owner_link = token_of(last_mail(mail_client, EMAIL))
    stranger = from_ip(mail_client, "198.51.100.7")
    assert [forgot(stranger).status_code for _ in range(2)] == [202, 202]
    assert len(token_rows(mail_client)) == et.MAX_LIVE_TOKENS  # the owner's link is still among the live ones
    assert forgot(stranger).status_code == 202
    assert forgot(stranger).status_code == 429  # one IP cannot go past its own 3 for this address
    assert forgot(mail_client).status_code == 202  # the owner's own budget is untouched
    latest = token_of(last_mail(mail_client, EMAIL))
    assert mail_client.post(RESET, json={"token": latest, "new_password": STRONG}).status_code == 200


def test_the_owners_link_survives_two_strangers_requests(mail_client):
    known_account(mail_client)
    forgot(mail_client)
    owner_link = token_of(last_mail(mail_client, EMAIL))
    stranger = from_ip(mail_client, "198.51.100.7")
    forgot(stranger)
    forgot(stranger)
    assert mail_client.post(RESET, json={"token": owner_link, "new_password": STRONG}).status_code == 200


def test_the_per_address_budget_is_ten_across_addresses(mail_client):
    known_account(mail_client)
    results = [ask(from_ip(mail_client, f"198.51.100.{i // 3 + 1}")).status_code for i in range(12)]
    assert results == [202] * 10 + [429] * 2
    assert from_ip(mail_client, "198.51.100.99").post(REQUEST, json={"email": "ghost@example.com"}).status_code == 202


def test_reset_token_cannot_be_used_to_sign_in(mail_client):
    known_account(mail_client)
    forgot(mail_client)
    token = token_of(last_mail(mail_client, EMAIL))
    assert mail_client.post(MAGIC, json={"token": token}).status_code == 401
    assert mail_client.post("/auth/email/verify", json={"token": token}).status_code == 400


def test_timing_work_is_equal_for_known_and_unknown(mail_client, monkeypatch):
    """Both paths hash a token and compute a code MAC (a dummy one for unknown addresses)."""
    known_account(mail_client)
    calls = []
    real = et.hash_token
    monkeypatch.setattr(et, "hash_token", lambda t: calls.append(1) or real(t))
    ask(mail_client, EMAIL)
    known_calls = len(calls)
    calls.clear()
    ask(mail_client, "ghost@example.com")
    assert len(calls) == known_calls == 1
