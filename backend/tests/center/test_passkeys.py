"""Passkey (WebAuthn) sign-in: link, sign in without a username, manage, sign up, and every way to fail."""

import json
import logging
import os

import pytest
from sqlalchemy import func, select

from api.center import passkeys as pk
from api.center.models import Passkey, User
from tests.center.fakes import fake_google_verifier
from tests.center.helpers import CREDS, csrf, register, grant_fresh
from tests.center.webauthn_helper import BE, BS, ES256, EDDSA, RS256, UP, UV, SoftAuthenticator, b64, unb64

PW = {"password": CREDS["password"]}
FAILED = {"detail": "Passkey sign-in failed"}
REG_FAILED = {"detail": "Passkey registration failed"}
COOKIES = {"sn_token", "sn_refresh"}


def cookie_names(response):
    return {c.split("=")[0] for c in response.headers.get_list("set-cookie")}


def rows(client, model=Passkey):
    with client.app.state.session_factory() as db:
        return list(db.scalars(select(model).order_by(model.id)))


def stored(client) -> Passkey:
    return rows(client)[0]


def link_options(client, session, body=PW):
    return client.post("/auth/me/passkeys/options", json=body, headers=csrf(session))


def add(client, session, credential, token, **extra):
    body = {"credential": credential, "challenge_token": token, **extra}
    return client.post("/auth/me/passkeys", json=body, headers=csrf(session))


def link(client, session, auth=None, body=PW, name=None, **create):
    """Run the whole linking ceremony; returns (authenticator, options, add-response)."""
    auth = auth or SoftAuthenticator()
    data = link_options(client, session, body).json()
    credential = auth.create(data["options"], **create)
    extra = {"name": name} if name else {}
    return auth, data, add(client, session, credential, data["challenge_token"], **extra)


def delete(client, url, session=None, body=None):
    return client.request("DELETE", url, json=body, headers=csrf(session) if session else {})


def login_options(client):
    response = client.post("/auth/passkey/options")
    assert response.status_code == 200, response.text
    return response.json()


def login(client, credential, token):
    return client.post("/auth/passkey/login", json={"credential": credential, "challenge_token": token})


def sign_in(client, auth, handle=None, **get):
    data = login_options(client)
    return login(client, auth.get(data["options"], user_handle=handle, **get), data["challenge_token"])


def handle_of(data) -> bytes:
    return unb64(data["options"]["user"]["id"])


@pytest.fixture
def linked(client):
    """Alice (password) with one ES256 passkey. (client, session, authenticator, user handle)."""
    session = register(client)
    auth, data, response = link(client, session)
    assert response.status_code == 200, response.text
    client.cookies.clear()
    return client, session, auth, handle_of(data)


def passkey_only(client, username=None):
    """A brand new account created by a passkey alone. (session, authenticator, user handle)."""
    body = {"username": username} if username else {}
    data = client.post("/auth/register/passkey/options", json=body).json()
    auth = SoftAuthenticator()
    extra = {"username": username} if username else None
    response = client.post("/auth/register/combined", data=signup_form(auth, data, extra))
    assert response.status_code == 201, response.text
    return response.json(), auth, handle_of(data)


def signup_form(auth, data, extra=None, **create):
    credential = auth.create(data["options"], **create)
    return {
        "passkey_credential": json.dumps(credential), "passkey_challenge_token": data["challenge_token"],
        **(extra or {}),
    }  # fmt: skip


def forged_token(purpose, challenge, **kw):
    return pk.mint_challenge(purpose, challenge, **kw)


# --- options ---------------------------------------------------------------------------------------


def test_login_options_are_discoverable_and_demand_user_verification(client):
    data = client.post("/auth/passkey/options").json()
    options = data["options"]
    assert options["rpId"] == "localhost" and options["userVerification"] == "required"
    assert options.get("allowCredentials", []) == []
    assert len(unb64(options["challenge"])) >= 32 and data["challenge_token"]


def test_link_options_demand_resident_key_uv_none_attestation_and_algorithms(client):
    session = register(client)
    options = link_options(client, session).json()["options"]
    assert options["rp"] == {"name": "Mạng xã hội", "id": "localhost"}
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["attestation"] == "none"
    assert [p["alg"] for p in options["pubKeyCredParams"]] == [-7, -257, -8]
    assert options["user"]["name"] == "Alice" and len(unb64(options["user"]["id"])) == 32


def test_link_options_exclude_existing_passkeys_and_reuse_the_user_handle(linked):
    client, session, auth, handle = linked
    client.post("/auth/login", json=CREDS)
    session = client.get("/auth/me").json()
    data = link_options(client, session).json()
    excluded = [unb64(c["id"]) for c in data["options"]["excludeCredentials"]]
    assert excluded == [auth.credential_id] and handle_of(data) == handle


def test_link_options_need_login_csrf_and_the_password(client):
    assert client.post("/auth/me/passkeys/options", json=PW).status_code == 401
    session = register(client)
    assert client.post("/auth/me/passkeys/options", json=PW).status_code == 403  # no csrf
    wrong = link_options(client, session, {"password": "nope-nope-nope"})
    assert (wrong.status_code, wrong.json()) == (403, {"detail": "Incorrect password"})
    assert link_options(client, session, {}).status_code == 403
    assert link_options(client, session).status_code == 200


# --- linking ----------------------------------------------------------------------------------------


def test_link_a_passkey_happy_path(client):
    session = register(client)
    _, data, response = link(client, session, name="  My phone ")
    assert response.status_code == 200
    (item,) = response.json()["passkeys"]
    assert set(item) == {"id", "name", "created_at", "last_used_at", "backed_up", "transports"}
    assert item["name"] == "My phone" and item["last_used_at"] is None
    assert item["backed_up"] is True and item["transports"] == ["internal"]
    row = stored(client)
    assert row.user_handle == handle_of(data) and row.sign_count == 0 and row.user_id == session["id"]
    me = client.get("/auth/me").json()
    assert me["passkey_count"] == 1 and me["passkeys"] == response.json()["passkeys"]


def test_link_defaults_the_name_and_uses_one_handle_for_every_passkey(client):
    session = register(client)
    link(client, session)
    _, _, second = link(client, session, name="")
    assert [p["name"] for p in second.json()["passkeys"]] == ["Passkey", "Passkey"]
    first, last = rows(client)
    assert first.user_handle == last.user_handle and first.credential_id != last.credential_id


@pytest.mark.parametrize("alg", [ES256, RS256, EDDSA])
def test_every_supported_algorithm_links_and_signs_in(client, alg):
    session = register(client)
    auth, data, response = link(client, session, SoftAuthenticator(alg))
    assert response.status_code == 200
    client.cookies.clear()
    signed = sign_in(client, auth, handle_of(data))
    assert signed.status_code == 200 and cookie_names(signed) == COOKIES


def test_link_roundtrip_options_to_verify(client):
    """The server's own options feed the authenticator and the result verifies (challenge from options)."""
    session = register(client)
    data = link_options(client, session).json()
    credential = SoftAuthenticator().create(data["options"])
    assert add(client, session, credential, data["challenge_token"]).status_code == 200


def test_duplicate_credential_is_409(client):
    session = register(client)
    auth, _, _ = link(client, session)
    _, _, again = link(client, session, auth)
    assert (again.status_code, again.json()) == (409, {"detail": "This passkey is already registered"})
    assert len(rows(client)) == 1


def test_duplicate_credential_of_another_account_is_409(client):
    session = register(client)
    auth, _, _ = link(client, session)
    client.cookies.clear()
    other = register(client, {"username": "bob", "password": "Bobs-Secret-1"})
    _, _, again = link(client, other, auth, body={"password": "Bobs-Secret-1"})
    assert again.status_code == 409


BAD_CREATE = {
    "origin": {"origin": "https://evil.example"},
    "rp id": {"rp_id": "evil.example"},
    "no user verification": {"flags": UP},
    "wrong client data type": {"kind": "webauthn.get"},
    "wrong challenge": {"challenge": b"\x01" * 32},
}


@pytest.mark.parametrize("create", BAD_CREATE.values(), ids=BAD_CREATE.keys())
def test_link_rejects_a_bad_registration(client, create):
    session = register(client)
    _, _, response = link(client, session, **create)
    assert (response.status_code, response.json()) == (400, REG_FAILED)
    assert rows(client) == []


def test_link_rejects_garbage_credentials(client):
    session = register(client)
    token = link_options(client, session).json()["challenge_token"]
    for credential in ({}, {"id": 5}, {"id": "a", "rawId": "a", "response": {}, "type": "public-key"}):
        assert add(client, session, credential, token).json() == REG_FAILED


def token_cases(client, session):
    """name -> (token, credential-for-that-challenge) for tokens that must be refused."""
    challenge = os.urandom(32)
    options = {"challenge": b64(challenge)}
    credential = SoftAuthenticator().create(options)
    me = session["id"]
    good = forged_token(pk.LINK, challenge, user_id=me, user_handle=os.urandom(32))
    head, payload, sig = good.split(".")
    return {
        "tampered": (f"{head}.{payload[:-3]}AAA.{sig}", credential),
        "expired": (forged_token(pk.LINK, challenge, user_id=me, user_handle=b"h" * 32, ttl_seconds=-5), credential),
        "login purpose": (forged_token(pk.LOGIN, challenge, user_id=me, user_handle=b"h" * 32), credential),
        "signup purpose": (forged_token(pk.SIGNUP, challenge, user_id=me, user_handle=b"h" * 32), credential),
        "another account": (forged_token(pk.LINK, challenge, user_id=me + 1, user_handle=b"h" * 32), credential),
        "garbage": ("not-a-token", credential),
    }  # fmt: skip


def test_link_rejects_bad_challenge_tokens(client):
    session = register(client)
    for name, (token, credential) in token_cases(client, session).items():
        response = add(client, session, credential, token)
        assert (response.status_code, response.json()) == (400, REG_FAILED), name
    assert rows(client) == []


def test_a_link_challenge_token_works_only_once(client):
    session = register(client)
    auth = SoftAuthenticator()
    data = link_options(client, session).json()
    credential = auth.create(data["options"])
    assert add(client, session, credential, data["challenge_token"]).status_code == 200
    again = add(client, session, credential, data["challenge_token"])
    assert (again.status_code, again.json()) == (400, REG_FAILED)


def test_a_failed_attempt_still_burns_the_challenge(client):
    session = register(client)
    data = link_options(client, session).json()
    bad = SoftAuthenticator().create(data["options"], origin="https://evil.example")
    assert add(client, session, bad, data["challenge_token"]).status_code == 400
    good = SoftAuthenticator().create(data["options"])
    assert add(client, session, good, data["challenge_token"]).status_code == 400


def test_a_challenge_token_is_never_an_access_token(client):
    data = login_options(client)
    client.cookies.set("sn_token", data["challenge_token"])
    assert client.get("/auth/me").status_code == 401


def test_link_needs_csrf_and_login(client):
    session = register(client)
    auth = SoftAuthenticator()
    data = link_options(client, session).json()
    credential = auth.create(data["options"])
    body = {"credential": credential, "challenge_token": data["challenge_token"]}
    assert client.post("/auth/me/passkeys", json=body).status_code == 403
    client.cookies.clear()
    assert client.post("/auth/me/passkeys", json=body, headers=csrf(session)).status_code == 401


# --- sign in -----------------------------------------------------------------------------------------


def test_sign_in_without_a_username(linked):
    client, _, auth, handle = linked
    response = sign_in(client, auth, handle)
    assert response.status_code == 200 and cookie_names(response) == COOKIES
    assert response.json()["username"] == "Alice"
    me = client.get("/auth/me")
    assert me.status_code == 200 and me.json()["passkey_count"] == 1


def test_sign_in_updates_counter_last_used_and_backup_state(linked):
    client, _, auth, handle = linked
    assert sign_in(client, auth, handle, counter=7, flags=UP | UV).status_code == 200
    row = stored(client)
    assert row.sign_count == 7 and row.last_used_at is not None and row.backed_up is False
    assert sign_in(client, auth, handle, counter=8, flags=UP | UV | BE | BS).status_code == 200
    assert stored(client).backed_up is True


def test_sign_in_with_or_without_the_user_handle(linked):
    client, _, auth, handle = linked
    assert sign_in(client, auth, None).status_code == 200
    assert sign_in(client, auth, handle).status_code == 200


def test_sign_in_with_a_two_factor_account_still_issues_a_session(linked):
    client, _, auth, handle = linked
    assert sign_in(client, auth, handle).json()["group"] == "user"


def assert_generic_failure(response):
    assert response.status_code == 401
    assert response.json() == FAILED
    assert "sn_token" not in cookie_names(response)


def test_every_sign_in_failure_is_the_same_401(linked):
    client, _, auth, handle = linked
    other = SoftAuthenticator()
    bad = {
        "user handle mismatch": lambda o: auth.get(o, user_handle=b"x" * 32),
        "unknown credential": lambda o: other.get(o, user_handle=handle),
        "bad signature": lambda o: auth.get(o, user_handle=handle, signature=b"\x30\x06" + b"\x00" * 6),
        "origin": lambda o: auth.get(o, user_handle=handle, origin="https://evil.example"),
        "rp id": lambda o: auth.get(o, user_handle=handle, rp_id="evil.example"),
        "no user verification": lambda o: auth.get(o, user_handle=handle, flags=UP),
        "no user presence": lambda o: auth.get(o, user_handle=handle, flags=UV),
        "challenge": lambda o: auth.get(o, user_handle=handle, challenge=b"\x02" * 32),
        "client data type": lambda o: auth.get(o, user_handle=handle, kind="webauthn.create"),
        "garbage": lambda o: {"id": "x"},
    }  # fmt: skip
    seen = set()
    for name, build in bad.items():
        client.app.state.passkey_login_throttle.reset("testclient")
        data = login_options(client)
        response = login(client, build(data["options"]), data["challenge_token"])
        assert_generic_failure(response)
        seen.add(response.text)
    assert len(seen) == 1
    assert stored(client).sign_count == 0 and stored(client).last_used_at is None


def test_sign_in_rejects_bad_challenge_tokens(linked):
    client, _, auth, handle = linked
    challenge = os.urandom(32)
    credential = auth.get({"challenge": b64(challenge)}, user_handle=handle)
    good = forged_token(pk.LOGIN, challenge)
    head, payload, sig = good.split(".")
    for token in (
        f"{head}.{payload[:-3]}AAA.{sig}",
        forged_token(pk.LOGIN, challenge, ttl_seconds=-5),
        forged_token(pk.LINK, challenge, user_id=1, user_handle=handle),
        forged_token(pk.SIGNUP, challenge, user_handle=handle),
        "garbage",
    ):
        client.app.state.passkey_login_throttle.reset("testclient")
        assert_generic_failure(login(client, credential, token))


def test_a_sign_in_challenge_works_once(linked):
    client, _, auth, handle = linked
    data = login_options(client)
    credential = auth.get(data["options"], user_handle=handle)
    assert login(client, credential, data["challenge_token"]).status_code == 200
    replay = login(client, credential, data["challenge_token"])
    assert_generic_failure(replay)


def test_sign_in_with_a_removed_passkey_fails(linked):
    client, _, auth, handle = linked
    client.post("/auth/login", json=CREDS)
    me = client.get("/auth/me").json()
    delete(client, f"/auth/me/passkeys/{me['passkeys'][0]['id']}", me, PW)
    client.cookies.clear()
    assert_generic_failure(sign_in(client, auth, handle))


# --- sign counter ------------------------------------------------------------------------------------


def test_sign_count_regression_is_rejected_audited_and_not_stored(linked, caplog):
    client, _, auth, handle = linked
    assert sign_in(client, auth, handle, counter=5).status_code == 200
    caplog.set_level(logging.INFO, logger="auth.audit")
    for counter in (5, 3, 0):
        client.app.state.passkey_login_throttle.reset("testclient")
        assert_generic_failure(sign_in(client, auth, handle, counter=counter))
    assert stored(client).sign_count == 5
    assert "possible cloned authenticator" in caplog.text
    assert sign_in(client, auth, handle, counter=6).status_code == 200


def test_an_all_zero_counter_stays_allowed(linked):
    client, _, auth, handle = linked
    for _ in range(3):
        assert sign_in(client, auth, handle, counter=0).status_code == 200
    assert stored(client).sign_count == 0


def test_sign_count_rule():
    assert not pk.sign_count_regressed(0, 0)
    assert not pk.sign_count_regressed(0, 1)
    assert pk.sign_count_regressed(1, 0) and pk.sign_count_regressed(4, 4) and pk.sign_count_regressed(4, 3)
    assert not pk.sign_count_regressed(4, 5)


# --- throttles ---------------------------------------------------------------------------------------


def test_option_requests_are_throttled_per_address(client):
    from api.center.main import PASSKEY_OPTIONS_MAX_PER_IP

    for _ in range(PASSKEY_OPTIONS_MAX_PER_IP):
        assert client.post("/auth/passkey/options").status_code == 200
    assert client.post("/auth/passkey/options").status_code == 429
    assert client.post("/auth/register/passkey/options", json={}).status_code == 429


def test_failed_sign_ins_are_throttled_then_even_a_good_one_waits(linked):
    from api.center.main import PASSKEY_LOGIN_MAX_FAILURES_PER_IP

    client, _, auth, handle = linked
    for _ in range(PASSKEY_LOGIN_MAX_FAILURES_PER_IP):
        assert_generic_failure(login(client, {}, "garbage"))
    assert sign_in(client, auth, handle).status_code == 429
    client.app.state.passkey_login_throttle.reset("testclient")
    assert sign_in(client, auth, handle).status_code == 200


def test_a_successful_sign_in_clears_the_failure_count(linked):
    client, _, auth, handle = linked
    for _ in range(5):
        login(client, {}, "garbage")
    assert sign_in(client, auth, handle).status_code == 200
    assert client.app.state.passkey_login_throttle.tracked_keys() == 0


# --- list / rename / delete --------------------------------------------------------------------------


def second_user(client):
    client.cookies.clear()
    session = register(client, {"username": "bob", "password": "Bobs-Secret-1"})
    auth, _, response = link(client, session, body={"password": "Bobs-Secret-1"})
    assert response.status_code == 200
    return session, response.json()["passkeys"][0]["id"]


def test_list_rename_delete(client):
    session = register(client)
    link(client, session, name="one")
    _, _, two = link(client, session, name="two")
    first, second = two.json()["passkeys"]
    assert client.get("/auth/me/passkeys").json() == two.json()
    renamed = client.patch(f"/auth/me/passkeys/{first['id']}", json={"name": " Laptop "}, headers=csrf(session))
    assert [p["name"] for p in renamed.json()["passkeys"]] == ["Laptop", "two"]
    deleted = delete(client, f"/auth/me/passkeys/{first['id']}", session, PW)
    assert [p["id"] for p in deleted.json()["passkeys"]] == [second["id"]]
    assert len(rows(client)) == 1


def test_list_needs_login(client):
    assert client.get("/auth/me/passkeys").status_code == 401


def test_rename_validates_and_needs_csrf(client):
    session = register(client)
    _, _, response = link(client, session)
    url = f"/auth/me/passkeys/{response.json()['passkeys'][0]['id']}"
    assert client.patch(url, json={"name": "x"}).status_code == 403
    for name in ("", "   ", "x" * 65):
        assert client.patch(url, json={"name": name}, headers=csrf(session)).status_code == 422
    assert client.patch(url, json={"name": "x" * 64}, headers=csrf(session)).status_code == 200


def test_other_peoples_passkeys_are_404(client):
    session = register(client)
    link(client, session)
    bob, bob_id = second_user(client)
    mine = rows(client)[0].id
    assert mine != bob_id
    rename = client.patch(f"/auth/me/passkeys/{mine}", json={"name": "hacked"}, headers=csrf(bob))
    remove = delete(client, f"/auth/me/passkeys/{mine}", bob, {"password": "Bobs-Secret-1"})
    assert rename.status_code == 404 and remove.status_code == 404
    assert delete(client, "/auth/me/passkeys/9999", bob).status_code == 404
    assert [p.name for p in rows(client)] == ["Passkey", "Passkey"]
    assert client.get("/auth/me/passkeys").json()["passkeys"][0]["id"] == bob_id


def test_delete_needs_the_password_when_the_account_has_one(client):
    session = register(client)
    _, _, response = link(client, session)
    url = f"/auth/me/passkeys/{response.json()['passkeys'][0]['id']}"
    assert delete(client, url, session).status_code == 403
    assert delete(client, url, session, {"password": "wrong-wrong-1"}).status_code == 403
    assert delete(client, url).status_code == 403  # csrf
    assert len(rows(client)) == 1
    assert delete(client, url, session, PW).status_code == 200


def test_the_last_passkey_of_a_passkey_only_account_cannot_go(client):
    session, auth, _ = passkey_only(client)
    grant_fresh(client)
    (item,) = client.get("/auth/me/passkeys").json()["passkeys"]
    response = client.delete(f"/auth/me/passkeys/{item['id']}", headers=csrf(session))
    assert (response.status_code, response.json()) == (409, {"detail": "Keep at least one sign-in method"})
    assert len(rows(client)) == 1


def test_one_of_two_passkeys_can_go_on_a_passkey_only_account(client):
    session, auth, _ = passkey_only(client)
    grant_fresh(client)
    _, _, added = link(client, session, body={})
    assert added.status_code == 200
    first, _ = added.json()["passkeys"]
    assert client.delete(f"/auth/me/passkeys/{first['id']}", headers=csrf(session)).status_code == 200
    (last,) = client.get("/auth/me/passkeys").json()["passkeys"]
    assert client.delete(f"/auth/me/passkeys/{last['id']}", headers=csrf(session)).status_code == 409


# --- usable_methods ----------------------------------------------------------------------------------


def test_usable_methods_counts_passkeys_once():
    from api.center.methods import usable_methods
    from api.center.passwords import NO_PASSWORD

    user = User(username="u", password_hash=NO_PASSWORD)
    assert usable_methods(user) == 0
    user.passkeys.append(Passkey(credential_id=b"1", public_key=b"k", user_handle=b"h"))
    user.passkeys.append(Passkey(credential_id=b"2", public_key=b"k", user_handle=b"h"))
    assert usable_methods(user) == 1 and usable_methods(user, without="passkey") == 0
    user.google_sub = "g"
    assert usable_methods(user) == 2 and usable_methods(user, without="google") == 1


def test_google_can_be_unlinked_when_a_passkey_remains(google_client):
    client = google_client
    session = client.post("/auth/google", json={"id_token": "sub-1|g1@example.com"}).json()
    grant_fresh(google_client)
    assert client.delete("/auth/me/google", headers=csrf(session)).status_code == 409  # alone
    _, _, added = link(client, session, body={})
    assert added.status_code == 200
    assert client.delete("/auth/me/google", headers=csrf(session)).status_code == 200
    assert client.get("/auth/me").json()["passkey_count"] == 1


def test_a_passkey_makes_removing_the_last_biometric_legal_and_vice_versa(bio_client):
    client = bio_client
    session = client.post(
        "/auth/register/voice", data={"username": "vera"}, files={"audio": ("v.webm", b"vera-voice-sample")}
    ).json()
    grant_fresh(bio_client)
    assert client.delete("/auth/me/voice", headers=csrf(session)).status_code == 409
    _, _, added = link(client, session, body={})
    assert added.status_code == 200
    assert client.delete("/auth/me/voice", headers=csrf(session)).status_code == 200
    (item,) = client.get("/auth/me/passkeys").json()["passkeys"]
    assert client.delete(f"/auth/me/passkeys/{item['id']}", headers=csrf(session)).status_code == 409


def test_a_passkey_makes_removing_the_webcam_legal(bio_client):
    client = bio_client
    session = client.post(
        "/auth/register/webcam", data={"username": "cam"}, files={"video": ("c.webm", b"vera-camera-clip")}
    ).json()
    grant_fresh(bio_client)
    assert client.delete("/auth/me/webcam", headers=csrf(session)).status_code == 409
    link(client, session, body={})
    assert client.delete("/auth/me/webcam", headers=csrf(session)).status_code == 200


def test_delete_account_removes_the_passkeys(client):
    session = register(client)
    link(client, session)
    link(client, session)
    assert len(rows(client)) == 2
    assert client.request("DELETE", "/auth/me", json=PW, headers=csrf(session)).status_code == 204
    assert rows(client) == [] and rows(client, User) == []


def test_delete_account_of_a_passkey_only_account_is_allowed(client):
    session, _, _ = passkey_only(client)
    grant_fresh(client)
    assert client.request("DELETE", "/auth/me", headers=csrf(session)).status_code == 204
    assert rows(client) == []


# --- sign up -----------------------------------------------------------------------------------------


def test_sign_up_options_are_public_and_use_a_fresh_handle_each_time(client):
    first = client.post("/auth/register/passkey/options", json={}).json()
    second = client.post("/auth/register/passkey/options", json={"username": "Zed"}).json()
    assert handle_of(first) != handle_of(second) and len(handle_of(first)) == 32
    assert second["options"]["user"]["name"] == "Zed"
    assert first["options"]["authenticatorSelection"]["residentKey"] == "required"
    assert client.post("/auth/register/passkey/options").status_code == 422  # a JSON body is expected


def test_sign_up_with_a_passkey_alone_generates_a_username_and_signs_in_later(client):
    session, auth, handle = passkey_only(client)
    assert session["username"].startswith("user-") and len(session["username"]) == 11
    assert client.get("/auth/me").json()["passkey_count"] == 1
    user = rows(client, User)[0]
    assert user.has_password is False and rows(client)[0].user_handle == handle
    client.cookies.clear()
    again = sign_in(client, auth, handle)
    assert again.status_code == 200 and again.json()["username"] == session["username"]


def test_sign_up_with_a_passkey_and_a_chosen_username(client):
    session, _, _ = passkey_only(client, username="Pat")
    assert session["username"] == "Pat"


def test_sign_up_with_passkey_and_password_needs_a_username(client):
    data = client.post("/auth/register/passkey/options", json={}).json()
    auth = SoftAuthenticator()
    form = signup_form(auth, data, {"password": "Correct-Horse-Battery1"})
    response = client.post("/auth/register/combined", data=form)
    assert (response.status_code, response.json()) == (422, {"detail": "Choose a username"})
    assert rows(client, User) == []
    data = client.post("/auth/register/passkey/options", json={}).json()
    form = signup_form(auth, data, {"password": "Correct-Horse-Battery1", "username": "Pam"})
    ok = client.post("/auth/register/combined", data=form)
    assert ok.status_code == 201 and ok.json()["username"] == "Pam"
    me = client.get("/auth/me").json()
    assert me["has_password"] is True and me["passkey_count"] == 1


def test_sign_up_with_passkey_and_google(google_client):
    client = google_client
    data = client.post("/auth/register/passkey/options", json={}).json()
    form = signup_form(SoftAuthenticator(), data, {"google_id_token": "sub-9|nine@example.com"})
    response = client.post("/auth/register/combined", data=form)
    assert response.status_code == 201 and response.json()["username"].startswith("nine")
    me = client.get("/auth/me").json()
    assert me["google_linked"] is True and me["passkey_count"] == 1


SIGNUP_BAD = {
    "origin": {"origin": "https://evil.example"},
    "rp id": {"rp_id": "evil.example"},
    "no user verification": {"flags": UP},
    "wrong challenge": {"challenge": b"\x03" * 32},
}


@pytest.mark.parametrize("create", SIGNUP_BAD.values(), ids=SIGNUP_BAD.keys())
def test_sign_up_is_all_or_nothing_when_the_passkey_fails(client, create):
    data = client.post("/auth/register/passkey/options", json={}).json()
    form = signup_form(SoftAuthenticator(), data, {"password": "Correct-Horse-Battery1", "username": "pam"}, **create)
    response = client.post("/auth/register/combined", data=form)
    assert (response.status_code, response.json()) == (400, REG_FAILED)
    assert rows(client, User) == [] and rows(client) == []
    assert "sn_token" not in cookie_names(response)


def test_sign_up_rejects_bad_tokens_and_garbage_json(client):
    auth = SoftAuthenticator()
    data = client.post("/auth/register/passkey/options", json={}).json()
    credential = json.dumps(auth.create(data["options"]))
    challenge = unb64(data["options"]["challenge"])
    bad = (
        forged_token(pk.LINK, challenge, user_id=1, user_handle=b"h" * 32),
        forged_token(pk.LOGIN, challenge),
        forged_token(pk.SIGNUP, challenge, user_handle=b"h" * 32, ttl_seconds=-5),
        "garbage",
    )
    for token in bad:
        response = client.post(
            "/auth/register/combined", data={"passkey_credential": credential, "passkey_challenge_token": token}
        )
        assert response.json() == REG_FAILED
    junk = client.post(
        "/auth/register/combined", data={"passkey_credential": "{nope", "passkey_challenge_token": data["challenge_token"]}
    )
    assert junk.json() == REG_FAILED and rows(client, User) == []


def test_sign_up_token_works_once(client):
    data = client.post("/auth/register/passkey/options", json={}).json()
    form = signup_form(SoftAuthenticator(), data)
    assert client.post("/auth/register/combined", data=form).status_code == 201
    client.cookies.clear()
    again = client.post("/auth/register/combined", data=form)
    assert again.status_code == 400 and len(rows(client, User)) == 1


def test_sign_up_with_a_duplicate_credential_is_409(client):
    session, auth, _ = passkey_only(client)
    client.cookies.clear()
    data = client.post("/auth/register/passkey/options", json={}).json()
    response = client.post("/auth/register/combined", data=signup_form(auth, data))
    assert (response.status_code, response.json()) == (409, {"detail": "This passkey is already registered"})
    assert len(rows(client, User)) == 1


def test_sign_up_needs_both_passkey_fields_or_neither(client):
    data = client.post("/auth/register/passkey/options", json={}).json()
    credential = json.dumps(SoftAuthenticator().create(data["options"]))
    for form in (
        {"passkey_credential": credential, "username": "x1"},
        {"passkey_challenge_token": data["challenge_token"], "username": "x2"},
    ):
        assert client.post("/auth/register/combined", data=form).status_code == 422
    assert rows(client, User) == []
    assert client.post("/auth/register/combined", data={"username": "x3"}).status_code == 422  # no method at all


def test_a_taken_username_does_not_create_a_passkey_row(client):
    register(client)
    client.cookies.clear()
    data = client.post("/auth/register/passkey/options", json={}).json()
    form = signup_form(SoftAuthenticator(), data, {"password": "Correct-Horse-Battery1", "username": "alice"})
    assert client.post("/auth/register/combined", data=form).status_code == 409
    assert rows(client) == []


# --- schema, config, docs, audit ---------------------------------------------------------------------


def test_openapi_lists_the_passkey_paths(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"post"} <= set(paths["/auth/passkey/options"]) and "/auth/passkey/login" in paths
    assert set(paths["/auth/me/passkeys"]) == {"get", "post"}
    assert set(paths["/auth/me/passkeys/{passkey_id}"]) == {"patch", "delete"}
    assert "/auth/me/passkeys/options" in paths and "/auth/register/passkey/options" in paths


def test_audit_log_never_contains_credential_bytes(client, caplog):
    caplog.set_level(logging.INFO, logger="auth.audit")
    session = register(client)
    auth, data, _ = link(client, session)
    client.cookies.clear()
    options = login_options(client)
    credential = auth.get(options["options"], user_handle=handle_of(data), counter=0)
    login(client, credential, options["challenge_token"])
    bad = auth.get(login_options(client)["options"], counter=0, signature=b"zz")
    login(client, bad, "garbage")
    text = caplog.text
    assert "passkey" in text
    for secret in (
        b64(auth.credential_id), b64(handle_of(data)), credential["response"]["signature"],
        credential["response"]["clientDataJSON"], data["challenge_token"], options["challenge_token"],
    ):  # fmt: skip
        assert secret not in text


def test_old_schema_database_gets_the_passkeys_table(tmp_path):
    import sqlalchemy as sa
    from fastapi.testclient import TestClient

    from api.center.main import create_app
    from tests.center.test_migrate import make_old_db

    url = make_old_db(tmp_path / "old.db")
    assert "passkeys" not in sa.inspect(sa.create_engine(url)).get_table_names()
    with TestClient(create_app(url)) as client:
        assert "passkeys" in sa.inspect(client.app.state.session_factory.kw["bind"]).get_table_names()
        client.post("/auth/login", json={"username": "olduser", "password": "legacy-pass-1"})
        session = client.get("/auth/me").json()
        _, _, response = link(client, session, body={"password": "legacy-pass-1"})
        assert response.status_code == 200


def test_the_passkeys_table_has_the_agreed_columns_and_cascade(client):
    import sqlalchemy as sa

    engine = client.app.state.session_factory.kw["bind"]
    inspector = sa.inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("passkeys")}
    assert columns == {
        "id", "user_id", "credential_id", "public_key", "sign_count", "user_handle", "transports", "name",
        "backed_up", "created_at", "last_used_at",
    }  # fmt: skip
    (fk,) = inspector.get_foreign_keys("passkeys")
    assert fk["referred_table"] == "users" and fk["options"].get("ondelete") == "CASCADE"
    uniques = [i for i in inspector.get_indexes("passkeys") if i["unique"]]
    assert any(i["column_names"] == ["credential_id"] for i in uniques)


def settings_from(monkeypatch, **env):
    from api.center.config import Settings

    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings.from_env()


def test_rp_id_defaults_to_the_first_origin_host(monkeypatch):
    assert settings_from(monkeypatch).webauthn_rp_id == "localhost"
    s = settings_from(monkeypatch, ALLOWED_ORIGINS="https://app.example.com,https://other.example.com")
    assert s.webauthn_rp_id == "app.example.com" and s.webauthn_origins == s.allowed_origins
    assert s.webauthn_rp_name == "Mạng xã hội"


def test_rp_id_and_name_come_from_env(monkeypatch):
    s = settings_from(monkeypatch, WEBAUTHN_RP_ID="Example.com", WEBAUTHN_RP_NAME="Social")
    assert (s.webauthn_rp_id, s.webauthn_rp_name) == ("example.com", "Social")


def test_production_requires_an_explicit_rp_id(monkeypatch):
    from api.center.config import ConfigError

    prod = {"APP_ENV": "production", "COOKIE_SECURE": "1", "ALLOWED_ORIGINS": "https://app.example.com"}
    with pytest.raises(ConfigError, match="WEBAUTHN_RP_ID"):
        settings_from(monkeypatch, **prod)
    assert settings_from(monkeypatch, WEBAUTHN_RP_ID="example.com", **prod).webauthn_rp_id == "example.com"


def test_transports_are_sanitised():
    assert pk.sanitized_transports({"response": {"transports": ["usb", "bogus", 5, "usb", "hybrid"]}}) == "usb,hybrid"
    assert pk.sanitized_transports({"response": {"transports": "usb"}}) is None
    assert pk.sanitized_transports({"response": {"transports": []}}) is None
    assert pk.sanitized_transports("x") is None


def test_the_fake_google_helper_is_importable():
    assert callable(fake_google_verifier)
