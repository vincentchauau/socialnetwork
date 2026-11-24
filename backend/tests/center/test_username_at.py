"""'@' is an ordinary username character: such names work everywhere and never touch email-based lookups."""

import pytest
from sqlalchemy import select

from api.center.handles import ALLOWED_SPECIALS, HANDLE_RE, base_handle, is_valid_username
from api.center.mailtemplates import render
from api.center.models import User
from api.center.passwords import password_problem
from api.center.schemas import USERNAME_HINT
from api.center.usernames import unavailable
from tests.center.helpers import CREDS, STRONG, register
from tests.center.mail_helpers import EMAIL, code_of, last_mail, token_of, verified_account
from tests.center.test_rename import rename

PW = CREDS["password"]
AT_NAMES = ["User@123", "a@b.co", "@name1", "name@", "bob@example.com"]


def test_at_is_in_the_allowed_set_and_the_rest_stays_excluded():
    assert ALLOWED_SPECIALS == "._-!#$%&+=^~@"
    assert HANDLE_RE.match("ab@") and is_valid_username("User@123") and is_valid_username("@name1")
    assert not is_valid_username("@@@") and not is_valid_username("a@") and not is_valid_username("a b@c")
    assert "'@'" not in USERNAME_HINT and "@" in USERNAME_HINT


@pytest.mark.parametrize("name", AT_NAMES)
def test_register_and_login_with_an_at_name_in_any_case(client, name):
    assert register(client, {"username": name, "password": PW})["username"] == name
    for typed in (name, name.lower(), name.upper()):
        client.cookies.clear()
        response = client.post("/auth/login", json={"username": typed, "password": PW})
        assert response.status_code == 200 and response.json()["username"] == name
    other = client.post("/auth/register", json={"username": name.upper(), "password": STRONG})
    assert other.status_code == 409 and other.json()["detail"] == "Username already taken"


def test_rename_accepts_at_names(client):
    session = register(client)
    assert rename(client, session, "User@123").status_code == 200
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert user.username == "User@123"


def test_reserved_and_system_names_are_unaffected(client):
    assert client.post("/auth/register", json={"username": "ADMIN", "password": PW}).status_code == 409
    with client.app.state.session_factory() as db:
        assert unavailable(db, "root") and not unavailable(db, "root@x")


def test_a_username_that_looks_like_an_email_cannot_shadow_email_flows(mail_client):
    client = mail_client
    shadow = register(client, {"username": EMAIL, "password": PW})  # username 'alice@example.com'
    assert shadow["username"] == EMAIL
    client.cookies.clear()
    verified_account(client, {"username": "realalice", "password": "Other-Pass-9"}, EMAIL)
    client.cookies.clear()

    # sign-in by email code reaches the account that owns the ADDRESS, not the one named like it
    assert client.post("/auth/email/login/request", json={"email": EMAIL}).status_code == 202
    code = code_of(last_mail(client, EMAIL))
    signed_in = client.post("/auth/email/login/verify", json={"email": EMAIL, "code": code})
    assert signed_in.status_code == 200 and signed_in.json()["username"] == "realalice"

    # forgot-password resets the owner of the address; the lookalike account keeps its password
    client.cookies.clear()
    assert client.post("/auth/password/forgot", json={"email": EMAIL}).status_code == 202
    token = token_of(last_mail(client, EMAIL))
    reset = client.post("/auth/password/reset", json={"token": token, "new_password": STRONG})
    assert reset.status_code == 200
    assert client.post("/auth/login", json={"username": "realalice", "password": STRONG}).status_code == 200
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": EMAIL, "password": PW}).status_code == 200
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": EMAIL, "password": STRONG}).status_code == 401


def test_email_flows_ignore_an_account_whose_username_equals_the_address(mail_client):
    register(mail_client, {"username": EMAIL, "password": PW})  # no email on it
    mail_client.cookies.clear()
    assert mail_client.post("/auth/password/forgot", json={"email": EMAIL}).status_code == 202
    assert mail_client.post("/auth/email/login/request", json={"email": EMAIL}).status_code == 202
    assert mail_client.app.state.mailer.to(EMAIL) == []


def test_generated_google_handles_never_contain_at():
    assert base_handle("we@ird+x@example.com") == "we0"
    assert base_handle("a" * 40 + "@example.com") == "a" * 32
    assert base_handle("x@example.com") == "x00"


def test_mail_notice_escapes_an_at_name():
    mail = render("password_changed", username="<b>@x")
    assert "&lt;b&gt;@x" in mail.html and "<b>" not in mail.html


@pytest.mark.parametrize(("username", "password"), [("User@123", "User@123"), ("user@123", "User@123"), ("USER@123", "User@123")])
def test_a_password_equal_to_the_username_is_accepted(client, username, password):
    assert password_problem(password) is None
    assert register(client, {"username": username, "password": password})["username"] == username
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200
