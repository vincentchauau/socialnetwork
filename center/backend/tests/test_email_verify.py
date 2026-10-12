"""Adding and verifying an email address (link and code), the 409 rules, removal and the guard."""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app import emailtokens as et
from app.models import EmailToken, User
from tests.helpers import CREDS, csrf, register
from tests.mail_helpers import (
    EMAIL, PUBLIC_URL, PW, add_email, age_tokens, code_of, last_mail, link_of, sent_to, set_user, token_of,
    token_rows, user_row, verified_account, verify_by_link,
)  # fmt: skip

BOB = {"username": "Bob", "password": "bobs-secret-1"}


def test_constants():
    assert (et.VERIFY_TTL.total_seconds(), et.LOGIN_TTL.total_seconds(), et.RESET_TTL.total_seconds()) == (
        24 * 3600, 15 * 60, 30 * 60,
    )
    assert et.MAX_CODE_ATTEMPTS == 5


def test_add_email_sends_link_and_code_and_does_not_change_the_account_yet(mail_client):
    session = register(mail_client)

    response = add_email(mail_client, session)

    assert (response.status_code, response.json()) == (202, {"ok": True})
    mail = last_mail(mail_client, EMAIL)
    assert link_of(mail).startswith(f"{PUBLIC_URL}/verify-email#token=")
    assert "?token=" not in link_of(mail)
    assert len(code_of(mail)) == 6 and code_of(mail) not in link_of(mail)
    assert "alice" not in mail.subject.lower()
    user = user_row(mail_client)
    assert (user.email, user.email_verified) == (None, False)
    me = mail_client.get("/auth/me").json()
    assert (me["email"], me["email_verified"]) == (None, False)


def test_email_is_normalised(mail_client):
    session = register(mail_client)
    assert add_email(mail_client, session, "  Alice@Example.COM ").status_code == 202
    assert sent_to(mail_client, EMAIL)


def test_add_email_validates_and_needs_csrf_and_password(mail_client):
    session = register(mail_client)
    bad = add_email(mail_client, session, "not-an-email")
    assert bad.status_code == 422 and bad.json()["detail"].startswith("email:")
    assert add_email(mail_client, session, "a" * 250 + "@example.com").status_code == 422
    assert mail_client.post("/auth/me/email", json={"email": EMAIL, **PW}).status_code == 403
    assert add_email(mail_client, session, body={"password": "wrong-password"}).status_code == 403
    assert add_email(mail_client, session, body={}).status_code == 403
    mail_client.cookies.clear()
    assert add_email(mail_client, session).status_code == 401
    assert mail_client.app.state.mailer.sent == []


def test_verify_by_link_sets_the_address(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)

    response = verify_by_link(mail_client, EMAIL)

    assert (response.status_code, response.json()) == (200, {"email": EMAIL, "email_verified": True})
    user = user_row(mail_client)
    assert (user.email, user.email_verified) == (EMAIL, True)
    assert mail_client.get("/auth/me").json()["email_verified"] is True


def test_link_verification_is_public_and_needs_no_session(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail_client.cookies.clear()
    assert verify_by_link(mail_client, EMAIL).status_code == 200


def test_verify_by_code_needs_the_session(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    code = code_of(last_mail(mail_client, EMAIL))
    mail_client.cookies.clear()
    assert mail_client.post("/auth/email/verify", json={"code": code}).status_code == 401
    assert user_row(mail_client).email_verified is False


def test_verify_by_code(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)

    response = mail_client.post("/auth/email/verify", json={"code": code_of(last_mail(mail_client, EMAIL))})

    assert (response.status_code, response.json()) == (200, {"email": EMAIL, "email_verified": True})
    assert user_row(mail_client).email == EMAIL


def test_verify_needs_exactly_a_token_or_a_code(mail_client):
    register(mail_client)
    assert mail_client.post("/auth/email/verify", json={}).status_code == 422
    assert mail_client.post("/auth/email/verify", json={"token": "a", "code": "123456"}).status_code == 422


def test_wrong_codes_burn_only_the_code_after_five_attempts(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    wrong = "000000" if code_of(mail) != "000000" else "111111"

    for _ in range(et.MAX_CODE_ATTEMPTS):
        response = mail_client.post("/auth/email/verify", json={"code": wrong})
        assert (response.status_code, response.json()) == (400, {"detail": "Invalid or expired code"})

    assert mail_client.post("/auth/email/verify", json={"code": code_of(mail)}).status_code == 400  # the code is dead
    assert verify_by_link(mail_client, EMAIL).status_code == 200  # the link is not: it lives until its TTL
    assert user_row(mail_client).email == EMAIL


def test_four_wrong_codes_then_the_right_one_works(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    wrong = "000000" if code_of(mail) != "000000" else "111111"
    for _ in range(et.MAX_CODE_ATTEMPTS - 1):
        mail_client.post("/auth/email/verify", json={"code": wrong})
    assert mail_client.post("/auth/email/verify", json={"code": code_of(mail)}).status_code == 200


def test_token_and_code_are_single_use(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    assert verify_by_link(mail_client, EMAIL).status_code == 200
    again = verify_by_link(mail_client, EMAIL)
    assert (again.status_code, again.json()) == (400, {"detail": "Invalid or expired link"})
    assert mail_client.post("/auth/email/verify", json={"code": code_of(mail)}).status_code == 400


def test_expired_token_and_code(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    age_tokens(mail_client)
    assert verify_by_link(mail_client, EMAIL).json() == {"detail": "Invalid or expired link"}
    code = mail_client.post("/auth/email/verify", json={"code": code_of(mail)})
    assert (code.status_code, code.json()) == (400, {"detail": "Invalid or expired code"})
    assert user_row(mail_client).email is None


def test_tampered_and_unknown_tokens_fail(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    token = token_of(last_mail(mail_client, EMAIL))
    for bad in (token[:-1] + ("A" if token[-1] != "A" else "B"), token + "x", "", "x" * 300, "nope"):
        assert mail_client.post("/auth/email/verify", json={"token": bad}).status_code in (400, 422)
    assert user_row(mail_client).email is None


def test_only_a_hash_is_stored_and_the_code_is_keyed(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    (row,) = token_rows(mail_client)
    assert row.token_hash == et.hash_token(token_of(mail)) and token_of(mail) not in row.token_hash
    assert len(row.token_hash) == 64 and len(row.code_hash) == 64
    assert row.code_hash == et.code_mac(row.id, code_of(mail))
    assert row.code_hash != et.code_mac(row.id + 1, code_of(mail))  # bound to the row
    assert (row.purpose, row.email, row.attempts, row.used_at) == ("verify", EMAIL, 0, None)


def test_a_new_request_keeps_the_earlier_verify_links_alive_up_to_three(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    first = last_mail(mail_client, EMAIL)
    add_email(mail_client, session)
    assert len(token_rows(mail_client)) == 2
    add_email(mail_client, session)
    assert len(token_rows(mail_client)) == et.MAX_LIVE_TOKENS == 3
    assert mail_client.post("/auth/email/verify", json={"token": token_of(first)}).status_code == 200


def test_concurrent_double_submit_exactly_one_wins(mail_file_client):
    client = mail_file_client
    session = register(client)
    add_email(client, session)
    token = token_of(last_mail(client, EMAIL))

    def submit(_):
        return client.post("/auth/email/verify", json={"token": token}).status_code

    with ThreadPoolExecutor(4) as pool:
        codes = sorted(pool.map(submit, range(4)))

    assert codes == [200, 400, 400, 400]


def test_consume_is_conditional_on_unused(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    row_id = token_rows(mail_client)[0].id
    factory = mail_client.app.state.session_factory
    with factory() as first, factory() as second:
        assert et.consume(first, row_id) is True
        first.commit()
        assert et.consume(second, row_id) is False


def test_email_verified_by_another_account_looks_like_a_success_and_sends_nothing(mail_client):
    verified_account(mail_client)
    mail_client.cookies.clear()
    bob = register(mail_client, BOB)

    response = add_email(mail_client, bob, body={"password": BOB["password"]})

    assert (response.status_code, response.json()) == (202, {"ok": True})
    assert sent_to(mail_client, EMAIL) == []
    assert token_rows(mail_client) == []


def test_unverified_claims_never_block_and_the_first_verifier_wins(mail_client):
    alice = register(mail_client)
    assert add_email(mail_client, alice).status_code == 202
    mail_client.cookies.clear()
    bob = register(mail_client, BOB)
    assert add_email(mail_client, bob, body={"password": BOB["password"]}).status_code == 202
    bob_mail = last_mail(mail_client, EMAIL)

    assert verify_by_link(mail_client, EMAIL).status_code == 200  # Bob's mail is the latest one
    assert user_row(mail_client, "bob").email == EMAIL
    alice_mail = [m for m in sent_to(mail_client, EMAIL) if m is not bob_mail][0]
    late = mail_client.post("/auth/email/verify", json={"token": token_of(alice_mail)})
    assert late.status_code == 409
    assert user_row(mail_client, "alice").email is None


def test_changing_email_notifies_the_old_address_and_swaps_it(mail_client):
    session = verified_account(mail_client)
    assert add_email(mail_client, session, "new@example.com").status_code == 202
    assert user_row(mail_client).email == EMAIL  # unchanged until verified
    assert sent_to(mail_client, EMAIL) == []

    response = verify_by_link(mail_client, "new@example.com")
    assert response.json() == {"email": "new@example.com", "email_verified": True}

    (old,) = sent_to(mail_client, EMAIL)
    assert "n***@e***.com" in old.text and "new@example.com" not in old.text and "new@example.com" not in old.html
    assert len(sent_to(mail_client, "new@example.com")) == 1  # only the verification mail itself
    assert user_row(mail_client).email == "new@example.com"


def test_first_verification_sends_no_change_notice(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    before = len(mail_client.app.state.mailer.sent)
    verify_by_link(mail_client, EMAIL)
    assert len(mail_client.app.state.mailer.sent) == before


def test_resend_is_throttled_per_user(mail_client):
    session = register(mail_client)
    codes = [add_email(mail_client, session, f"box{i}@example.com").status_code for i in range(6)]
    assert codes == [202] * 5 + [429]


def test_resend_is_throttled_per_target_address_across_users(mail_client):
    first = register(mail_client)
    assert [add_email(mail_client, first).status_code for _ in range(3)] == [202] * 3
    mail_client.cookies.clear()
    bob = register(mail_client, BOB)
    body = {"password": BOB["password"]}
    blocked = add_email(mail_client, bob, body=body)
    assert (blocked.status_code, blocked.json()) == (429, {"detail": "Too many attempts, try later"})
    assert len(sent_to(mail_client, EMAIL)) == 3
    assert add_email(mail_client, bob, "other@example.com", body).status_code == 202


def test_a_taken_address_counts_against_the_target_budget_like_any_other(mail_client):
    verified_account(mail_client)
    mail_client.cookies.clear()
    bob = register(mail_client, BOB)
    codes = [add_email(mail_client, bob, body={"password": BOB["password"]}).status_code for _ in range(3)]
    assert codes == [202, 202, 429]  # the owner's own verification request was the first of the three


def test_verify_submissions_are_throttled_per_ip(mail_client):
    register(mail_client)
    codes = [mail_client.post("/auth/email/verify", json={"token": f"t{i}"}).status_code for i in range(21)]
    assert codes[:20] == [400] * 20 and codes[20] == 429


def test_remove_email_needs_csrf_and_password(mail_client):
    session = verified_account(mail_client)
    assert mail_client.request("DELETE", "/auth/me/email", json=PW).status_code == 403
    wrong = mail_client.request("DELETE", "/auth/me/email", json={"password": "nope-nope-nope"}, headers=csrf(session))
    assert wrong.status_code == 403
    assert user_row(mail_client).email == EMAIL


def test_remove_email(mail_client):
    session = verified_account(mail_client)
    response = mail_client.request("DELETE", "/auth/me/email", json=PW, headers=csrf(session))
    body = response.json()
    assert response.status_code == 200 and body["email_verified"] is False and body["has_password"] is True
    user = user_row(mail_client)
    assert (user.email, user.email_verified) == (None, False)


def test_removing_the_only_method_email_is_refused(mail_client):
    session = verified_account(mail_client)
    set_user(mail_client, password_hash="!")  # password gone: email is the only method left
    response = mail_client.request("DELETE", "/auth/me/email", headers=csrf(session))
    assert (response.status_code, response.json()) == (409, {"detail": "Keep at least one sign-in method"})
    assert user_row(mail_client).email == EMAIL


def test_removing_an_unverified_address_is_allowed(mail_client):
    session = register(mail_client)
    set_user(mail_client, email=EMAIL, email_verified=False)
    response = mail_client.request("DELETE", "/auth/me/email", json=PW, headers=csrf(session))
    assert response.status_code == 200 and user_row(mail_client).email is None


def test_usable_methods_counts_only_a_verified_email():
    from app.methods import usable_methods

    user = User(username="x", password_hash="!", email=EMAIL, email_verified=False)
    assert usable_methods(user) == 0
    user.email_verified = True
    assert usable_methods(user) == 1
    assert usable_methods(user, without="email") == 0
    assert usable_methods(user, without=("email", "google")) == 0


def test_a_verified_email_lets_other_methods_be_removed(mail_client):
    session = verified_account(mail_client)
    mail_client.post("/auth/me/google", json={"id_token": "sub-1|other@example.com", **PW}, headers=csrf(session))
    me = mail_client.request("DELETE", "/auth/me/google", json=PW, headers=csrf(session))
    assert me.status_code == 200


def test_google_unlink_is_refused_when_it_would_leave_no_method(mail_client):
    # Google-only account whose email (verified by Google) is wiped on unlink: nothing would remain
    created = mail_client.post("/auth/google", json={"id_token": "sub-7|gina@example.com"})
    assert created.status_code == 200
    me = mail_client.get("/auth/me").json()
    assert (me["email"], me["email_verified"]) == ("gina@example.com", True)
    response = mail_client.request("DELETE", "/auth/me/google", headers=csrf(me))
    assert (response.status_code, response.json()) == (409, {"detail": "Keep at least one sign-in method"})


def test_google_accounts_start_verified_and_linking_verifies(mail_client):
    mail_client.post("/auth/google", json={"id_token": "sub-8|gus@example.com"})
    assert user_row(mail_client, "gus").email_verified is True
    mail_client.cookies.clear()
    session = register(mail_client)
    linked = mail_client.post(
        "/auth/me/google", json={"id_token": "sub-9|alice.real@example.com", **PW}, headers=csrf(session)
    )
    assert (linked.json()["email"], linked.json()["email_verified"]) == ("alice.real@example.com", True)


def test_duplicate_google_email_is_not_stored_or_verified(mail_client):
    verified_account(mail_client)
    mail_client.cookies.clear()
    mail_client.post("/auth/google", json={"id_token": f"sub-10|{EMAIL}"})
    with mail_client.app.state.session_factory() as db:
        google_user = db.scalar(select(User).where(User.google_sub == "sub-10"))
    assert (google_user.email, google_user.email_verified) == (None, False)


def test_account_deletion_deletes_its_tokens(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    assert len(token_rows(mail_client)) == 1
    response = mail_client.request("DELETE", "/auth/me", json=PW, headers=csrf(session))
    assert response.status_code == 204
    assert token_rows(mail_client) == []


def test_old_rows_are_purged_on_write(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    age_tokens(mail_client)
    mail_client.cookies.clear()
    mail_client.post("/auth/email/login/request", json={"email": "someone@example.com"})  # a write elsewhere
    other = register(mail_client, BOB)
    add_email(mail_client, other, "bob@example.com", {"password": BOB["password"]})
    rows = token_rows(mail_client)
    assert [r.email for r in rows] == ["bob@example.com"]


def test_used_rows_are_purged_on_write(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    verify_by_link(mail_client, EMAIL)
    add_email(mail_client, session, "again@example.com")
    assert [r.email for r in token_rows(mail_client)] == ["again@example.com"]


def test_audit_log_masks_addresses_and_never_holds_secrets(mail_client, caplog):
    caplog.set_level(logging.INFO, logger="auth.audit")
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    verify_by_link(mail_client, EMAIL)
    log = caplog.text
    assert "a***@e***.com" in log
    assert EMAIL not in log and token_of(mail) not in log and code_of(mail) not in log


def test_mask_email():
    from app.mailer import mask_email

    assert mask_email("alice@example.com") == "a***@e***.com"
    assert mask_email("x@mail.co.uk") == "x***@m***.uk"
    assert mask_email("weird") == "***"
    assert mask_email(None) == "***"


def test_bodies_are_vietnamese_and_html_escaped(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    assert mail.html and "<" in mail.html and "xác" in mail.text.lower()
    assert mail.subject and any(ch in mail.subject for ch in "àáảãạăâđêôơưấềếệ")
    from app.mailtemplates import render

    hostile = render("password_changed", username="<script>alert(1)</script>")
    assert "<script>" not in hostile.html and "&lt;script&gt;" in hostile.html
