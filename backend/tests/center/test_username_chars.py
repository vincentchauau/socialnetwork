"""Usernames may contain letters, digits and ALLOWED_SPECIALS (whitespace, separators or non-ASCII)."""

import json
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from sqlalchemy import select

from api.center import handles, totp
from api.center.handles import ALLOWED_SPECIALS, HANDLE_RE, is_valid_username
from api.center.mailtemplates import render
from api.center.models import User
from api.center.schemas import USERNAME_HINT
from api.center.throttle import pair_key
from tests.center.helpers import CREDS, STRONG, register
from tests.center.test_rename import rename

PW = CREDS["password"]
REJECTED = ["has space", "ab:c", "a|bc", "a/bc", "a\\bc", "Nguyễn", "ab*", "ab?", "a'b", 'a"b', "a<b>", "a`b",
            "a[b]", "a{b}", "a(b)", "a,b", "a;b", "tab\tx", "new\nline", "ab\x00", "аdmin"]  # last: Cyrillic a


def test_allowed_set_is_one_constant_and_the_regex_is_built_from_it():
    assert ALLOWED_SPECIALS == "._-!#$%&+=^~@"
    for char in ALLOWED_SPECIALS:
        assert HANDLE_RE.match(f"ab{char}")


@pytest.mark.parametrize("char", list(ALLOWED_SPECIALS))
def test_register_and_login_with_each_allowed_special(client, char):
    name = f"Us{char}er9"
    assert register(client, {"username": name, "password": PW})["username"] == name
    for typed in (name, name.lower(), name.upper()):
        client.cookies.clear()
        response = client.post("/auth/login", json={"username": typed, "password": PW})
        assert response.status_code == 200 and response.json()["username"] == name
    other = client.post("/auth/register", json={"username": name.upper(), "password": STRONG})
    assert other.status_code == 409 and other.json()["detail"] == "Username already taken"


@pytest.mark.parametrize("name", REJECTED)
def test_register_rejects_forbidden_characters(client, name):
    response = client.post("/auth/register", json={"username": name, "password": PW})
    assert response.status_code == 422
    assert USERNAME_HINT in json.dumps(response.json(), ensure_ascii=False)


@pytest.mark.parametrize("name", ["...", "---", "!!!", "_._", "~~~", "$%&", "a." ])
def test_a_name_needs_a_letter_or_digit_and_three_characters(client, name):
    response = client.post("/auth/register", json={"username": name, "password": PW})
    assert response.status_code == 422
    assert "letter or digit" in USERNAME_HINT


def test_trailing_newline_is_not_accepted_by_the_validator():
    assert not is_valid_username("abc\n")
    assert is_valid_username("a!c") and not is_valid_username("a" * 33) and is_valid_username("a" * 32)
    assert handles.key_of("A!B") == "a!b"


def test_rename_accepts_special_characters_and_rejects_the_rest(client):
    session = register(client)
    assert rename(client, session, "a:b.co").status_code == 422
    assert rename(client, session, "a b").status_code == 422
    assert rename(client, session, "Neo#1!").status_code == 200
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert user.username == "Neo#1!"


def test_pair_key_is_injective_and_never_splits_ambiguously():
    parts = ["a", "a|", "|a", "a|b", "1:a", "", "b", "a!b", "a!", "!b", "1.2.3.4", "::1"]
    seen = {}
    for ip in parts:
        for name in parts:
            key = pair_key(ip, name)
            assert seen.setdefault(key, (ip, name)) == (ip, name)
    assert pair_key("1.2.3.4", "x") != "1.2.3.4"


def test_login_throttle_keys_do_not_collide_for_similar_special_names(client):
    register(client, {"username": "a!bc", "password": PW})
    client.cookies.clear()
    for _ in range(5):
        assert client.post("/auth/login", json={"username": "a!bc", "password": "wrong-pass-1"}).status_code == 401
    assert client.post("/auth/login", json={"username": "a!bc", "password": PW}).status_code == 429
    register_other = client.post("/auth/register", json={"username": "a!bd", "password": PW})
    assert register_other.status_code == 201
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": "a!bd", "password": PW}).status_code == 200


def test_mail_notice_escapes_html_in_every_special_name():
    name = "A&B<x>#$%^~"  # not registrable, but the template must stay safe whatever it is given
    mail = render("password_changed", username=name)
    assert "&lt;x&gt;" in mail.html and "<x>" not in mail.html
    assert name in mail.text
    for char in ALLOWED_SPECIALS:
        assert render("email_removed", username=f"u{char}x").text.count(f"u{char}x") == 1
    assert "A&amp;B" in mail.html


def test_otpauth_uri_percent_encodes_the_name():
    name = "a&b#c%d+e=f"
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", name)  # 160 bits: pyotp needs at least 112
    parsed = urlparse(uri)
    assert parsed.fragment == "" and unquote(parsed.path).endswith(name)
    assert set(parse_qs(parsed.query)) == {"secret", "issuer"}


def test_sql_lookup_treats_like_wildcards_literally(client):
    register(client, {"username": "ab_cd", "password": PW})
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": "abXcd", "password": PW}).status_code == 401
    assert client.post("/auth/login", json={"username": "ab%", "password": PW}).status_code == 401
