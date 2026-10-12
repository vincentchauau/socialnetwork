"""Four independent sign-in methods: register with, sign in with, link and remove each one."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import User
from app.passwords import NO_PASSWORD
from tests.fakes import fake_google_verifier
from tests.helpers import CREDS, csrf, register

PW = {"password": CREDS["password"]}
VOICE = ("v.webm", b"vera-voice-sample")
OTHER_VOICE = ("v.webm", b"someone-else-voice")
CAM = ("c.webm", b"vera-camera-clip")
OTHER_CAM = ("c.webm", b"someone-else-clip")
SILENT = ("c.webm", b"silent-clip")
BAD = ("b.webm", b"bad-sample")
FAILED = (401, '{"detail":"Biometric login failed"}')
COOKIES = {"sn_token", "sn_refresh"}


def cookie_names(response):
    return {c.split("=")[0] for c in response.headers.get_list("set-cookie")}


def reg_voice(c, username="vera", audio=VOICE):
    return c.post("/auth/register/voice", data={"username": username}, files={"audio": audio})


def reg_webcam(c, username="vera", video=CAM, audio=None):
    files = {"video": video, **({"audio": audio} if audio else {})}
    return c.post("/auth/register/webcam", data={"username": username}, files=files)


def combined(c, username="vera", data=None, **files):
    return c.post("/auth/register/combined", data={"username": username, **(data or {})}, files=files or None)


def login_voice(c, username="vera", audio=VOICE):
    return c.post("/auth/login/voice", data={"username": username}, files={"audio": audio} if audio else None)


def login_webcam(c, username="vera", video=CAM, audio=None):
    files = {**({"video": video} if video else {}), **({"audio": audio} if audio else {})}
    return c.post("/auth/login/webcam", data={"username": username}, files=files or None)


def unlock(c, username="vera"):
    state = c.app.state
    state.alone_throttle.reset(f"testclient|{username}")
    state.alone_account_throttle.reset(username)


def row(c, username="vera") -> User:
    with c.app.state.session_factory() as db:
        return db.scalar(select(User).where(User.username == username))


def flags(user):
    return (user.has_password, user.google_linked, user.voice_login, user.webcam_login,
            bool(user.audio_embedding), bool(user.face_embedding))  # fmt: skip


@pytest.fixture
def gclient(bio_client):
    bio_client.app.state.google_verifier = fake_google_verifier
    return bio_client


# --- registration: voice ----------------------------------------------------------------------


def test_register_voice_creates_a_passwordless_voice_account(bio_client):
    response = reg_voice(bio_client, "Vera")
    assert response.status_code == 201
    assert cookie_names(response) == COOKIES and response.json()["username"] == "vera"
    user = row(bio_client)
    assert user.password_hash == NO_PASSWORD and flags(user) == (False, False, True, False, True, False)
    assert b"vera-voice" not in user.audio_embedding
    me = bio_client.get("/auth/me").json()
    assert me["voice_login"] is True and me["has_password"] is False and "biometric_login" not in me


def test_register_voice_rejections(bio_client):
    assert reg_voice(bio_client, "vera").status_code == 201
    assert reg_voice(bio_client, "vera").status_code == 409
    assert reg_voice(bio_client, "ab").status_code == 422
    assert reg_voice(bio_client, "Bad Name!").status_code == 422
    assert reg_voice(bio_client, "bob", BAD).status_code == 400
    assert row(bio_client, "bob") is None
    assert reg_voice(bio_client, "bob", OTHER_VOICE).status_code == 201  # the failure did not burn the name
    assert bio_client.post("/auth/register/voice", data={"username": "zed"}).status_code == 422
    r = reg_voice(bio_client, "amy", ("a.webm", b"missing-lib"))
    assert r.status_code == 503 and "ffmpeg" not in r.text


def test_register_taken_by_a_password_account(bio_client):
    register(bio_client)
    bio_client.cookies.clear()
    assert reg_voice(bio_client, "alice").status_code == 409


# --- registration: webcam ---------------------------------------------------------------------


def test_register_webcam_stores_the_face_only(bio_client):
    assert reg_webcam(bio_client).status_code == 201
    user = row(bio_client)
    assert flags(user) == (False, False, False, True, False, True)  # no voice template at all
    assert bio_client.app.state.cipher.decrypt(user.face_embedding) == b"F:vera-camera-clip"


def test_register_webcam_ignores_an_audio_file(bio_client):
    assert reg_webcam(bio_client, audio=VOICE).status_code == 201
    user = row(bio_client)
    assert user.audio_embedding is None and user.face_embedding and user.voice_login is False


def test_register_webcam_with_a_silent_clip_is_fine(bio_client):
    assert reg_webcam(bio_client, video=SILENT).status_code == 201
    assert row(bio_client).audio_embedding is None


def test_register_webcam_rejections(bio_client):
    assert bio_client.post("/auth/register/webcam", data={"username": "vera"}).status_code == 422
    assert reg_webcam(bio_client, video=BAD).status_code == 400
    assert reg_webcam(bio_client, video=BAD, audio=VOICE).status_code == 400
    assert row(bio_client) is None
    assert reg_webcam(bio_client, audio=BAD).status_code == 201  # audio is never looked at
    assert reg_webcam(bio_client).status_code == 409
    assert reg_webcam(bio_client, "x").status_code == 422


def test_register_routes_are_503_when_biometrics_are_disabled(client):
    for response in (
        reg_voice(client),
        reg_webcam(client),
        login_voice(client),
        login_webcam(client),
    ):
        assert response.status_code == 503 and response.json() == {"detail": "Biometrics are not available"}


def test_register_throttle_is_shared_per_ip(bio_client):
    codes = [reg_voice(bio_client, f"user{i:02d}", ("v.webm", f"voice-{i}".encode())).status_code for i in range(11)]
    assert codes == [201] * 10 + [429]


# --- combined registration --------------------------------------------------------------------


@pytest.mark.parametrize(
    "data, files, expected",
    [
        ({"password": "correct-horse-battery"}, {}, (True, False, False, False, False, False)),
        ({}, {"voice_audio": VOICE}, (False, False, True, False, True, False)),
        ({}, {"webcam_video": CAM}, (False, False, False, True, False, True)),
        ({"password": "correct-horse-battery"}, {"voice_audio": VOICE}, (True, False, True, False, True, False)),
        ({"password": "correct-horse-battery"}, {"webcam_video": CAM}, (True, False, False, True, False, True)),
        ({"google_id_token": "g1|vera@example.com"}, {"voice_audio": VOICE}, (False, True, True, False, True, False)),
        ({"google_id_token": "g1|vera@example.com"}, {}, (False, True, False, False, False, False)),
        (
            {"password": "correct-horse-battery", "google_id_token": "g1|vera@example.com"},
            {"voice_audio": VOICE, "webcam_video": CAM},
            (True, True, True, True, True, True),
        ),
    ],
)
def test_combined_registration_sets_the_right_flags(gclient, data, files, expected):
    response = combined(gclient, "Vera", data, **files)
    assert response.status_code == 201 and cookie_names(response) == COOKIES
    user = row(gclient)
    assert flags(user) == expected
    assert (user.password_hash == NO_PASSWORD) is (not expected[0])
    assert gclient.get("/auth/me").json()["username"] == "vera"


def test_combined_with_voice_and_video_keeps_two_independent_templates(gclient):
    combined(gclient, webcam_video=CAM, voice_audio=VOICE)
    user = row(gclient)
    assert gclient.app.state.cipher.decrypt(user.audio_embedding) == b"A:vera-voice-sampl"
    assert gclient.app.state.cipher.decrypt(user.face_embedding) == b"F:vera-camera-clip"
    assert user.voice_login is True and user.webcam_login is True
    assert user.email is None  # no google


def test_combined_google_stores_the_email(gclient):
    combined(gclient, data={"google_id_token": "g1|vera@example.com"})
    assert row(gclient).email == "vera@example.com"


def test_combined_signs_in_with_every_chosen_method_afterwards(gclient):
    combined(gclient, data={"password": "correct-horse-battery"}, voice_audio=VOICE, webcam_video=CAM)
    gclient.cookies.clear()
    assert gclient.post("/auth/login", json={"username": "vera", "password": "correct-horse-battery"}).status_code == 200
    assert login_voice(gclient).status_code == 200
    assert login_webcam(gclient).status_code == 200  # face only: no voice involved


@pytest.mark.parametrize(
    "data, files, status_code",
    [
        ({"password": "correct-horse-battery"}, {"voice_audio": BAD}, 400),
        ({"password": "correct-horse-battery"}, {"webcam_video": BAD}, 400),
        ({"password": "short"}, {"voice_audio": VOICE}, 422),
        ({"google_id_token": "bad-token"}, {"voice_audio": VOICE}, 401),
        ({"password": "correct-horse-battery"}, {"voice_audio": VOICE, "webcam_video": BAD}, 400),
    ],
)
def test_combined_is_all_or_nothing(gclient, data, files, status_code):
    assert combined(gclient, data=data, **files).status_code == status_code
    with gclient.app.state.session_factory() as db:
        assert db.scalar(select(User.id)) is None


def test_combined_needs_a_method_and_a_valid_free_username(gclient):
    none = combined(gclient)
    assert none.status_code == 422 and none.json() == {"detail": "Choose at least one sign-in method"}
    assert combined(gclient, "ab", {"password": "correct-horse-battery"}).status_code == 422
    assert combined(gclient, data={"password": "correct-horse-battery"}).status_code == 201
    assert combined(gclient, data={"password": "correct-horse-battery"}).status_code == 409


def test_combined_google_conflict_creates_nothing(gclient):
    assert combined(gclient, "first", {"google_id_token": "g1|a@example.com"}).status_code == 201
    gclient.cookies.clear()
    r = combined(gclient, "second", {"google_id_token": "g1|a@example.com"}, voice_audio=VOICE)
    assert r.status_code == 409 and r.json() == {"detail": "That Google account is already linked to an account"}
    assert row(gclient, "second") is None


def test_combined_google_not_configured_is_503(bio_client):
    assert combined(bio_client, data={"google_id_token": "g1|a@example.com"}).status_code == 503


def test_combined_biometric_file_while_disabled_is_503_but_password_still_works(client):
    r = combined(client, voice_audio=VOICE)
    assert r.status_code == 503 and r.json() == {"detail": "Biometrics are not available"}
    assert row(client) is None
    assert combined(client, data={"password": "correct-horse-battery"}).status_code == 201


def test_combined_shares_the_register_throttle(bio_client):
    codes = [combined(bio_client, f"user{i:02d}", {"password": "correct-horse-battery"}).status_code for i in range(11)]
    assert codes == [201] * 10 + [429]


def test_combined_rejects_a_bad_origin(bio_client):
    r = bio_client.post(
        "/auth/register/combined", data={"username": "vera", "password": "correct-horse-battery"},
        headers={"Origin": "https://evil.example"},
    )  # fmt: skip
    assert r.status_code == 403


# --- voice sign-in ----------------------------------------------------------------------------


def test_voice_login_happy_path_uses_strict_threshold(bio_client):
    reg_voice(bio_client)
    bio_client.cookies.clear()
    response = login_voice(bio_client, "VERA")
    assert response.status_code == 200 and response.json()["username"] == "vera"
    assert cookie_names(response) == COOKIES and bio_client.get("/auth/me").status_code == 200
    assert set(bio_client.app.state.biometrics.strict_calls) == {True}


def test_voice_login_every_failure_is_the_same_response(bio_client):
    reg_voice(bio_client)
    register(bio_client)  # alice: password only
    reg_webcam(bio_client, "cam")  # voice template, voice_login off
    bio_client.cookies.clear()
    bad = [
        login_voice(bio_client, "ghost"),
        login_voice(bio_client, "alice"),
        login_voice(bio_client, "cam", ("v.webm", b"vera-camera-cli")),
        login_voice(bio_client, "vera", OTHER_VOICE),
        login_voice(bio_client, "vera", BAD),
        login_voice(bio_client, "vera", None),
    ]
    assert {(r.status_code, r.text) for r in bad} == {FAILED}


def test_webcam_registered_account_cannot_sign_in_by_voice(bio_client):
    reg_webcam(bio_client, audio=VOICE)
    bio_client.cookies.clear()
    assert (login_voice(bio_client).status_code, login_voice(bio_client).text) == FAILED


def test_voice_login_is_locked_after_three_tries(bio_client):
    reg_voice(bio_client)
    bio_client.cookies.clear()
    codes = [login_voice(bio_client, audio=OTHER_VOICE).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    assert login_voice(bio_client).status_code == 429


def test_voice_login_account_wide_lock_across_addresses(bio_client):
    reg_voice(bio_client)
    codes = [
        login_voice(TestClient(bio_client.app, client=(f"198.51.100.{i}", 5000)), audio=OTHER_VOICE).status_code
        for i in range(14)
    ]
    assert codes[0] == 401 and codes[-1] == 429


def test_voice_login_for_an_account_with_a_password_too(bio_client):
    session = register(bio_client)
    assert bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=csrf(session)).status_code == 200
    bio_client.cookies.clear()
    assert login_voice(bio_client, "alice").status_code == 200


# --- webcam sign-in ---------------------------------------------------------------------------


def test_webcam_login_happy_path(bio_client):
    reg_webcam(bio_client)
    bio_client.cookies.clear()
    response = login_webcam(bio_client, "Vera")
    assert response.status_code == 200 and cookie_names(response) == COOKIES
    assert set(bio_client.app.state.biometrics.strict_calls) == {True}


def test_webcam_login_failures_are_identical(bio_client):
    reg_webcam(bio_client)
    reg_voice(bio_client, "voiceonly")
    bio_client.cookies.clear()
    attempts = [
        ("ghost", CAM),
        ("voiceonly", ("c.webm", b"vera-voice-samp")),  # method not enabled
        ("vera", OTHER_CAM),  # wrong person
        ("vera", BAD),
        ("vera", None),
    ]
    bad = []
    for name, video in attempts:
        bad.append(login_webcam(bio_client, name, video))
        unlock(bio_client, name)
    assert {(r.status_code, r.text) for r in bad} == {FAILED}


def test_webcam_login_uses_the_face_only(bio_client):
    reg_webcam(bio_client, audio=VOICE)
    bio_client.cookies.clear()
    assert login_webcam(bio_client, audio=OTHER_VOICE).status_code == 200  # a wrong audio file does not matter
    bio_client.cookies.clear()
    assert login_webcam(bio_client, video=OTHER_CAM).status_code == 401  # another face
    unlock(bio_client)
    assert login_webcam(bio_client, video=CAM, audio=BAD).status_code == 200  # a bad audio file is never read
    bio_client.cookies.clear()
    assert login_webcam(bio_client).status_code == 200  # no audio at all
    bio_client.cookies.clear()
    assert login_webcam(bio_client, video=SILENT).status_code == 401  # a silent clip is just another face


def test_webcam_login_ignores_a_stale_voice_template(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=h)
    bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM}, headers=h)
    bio_client.cookies.clear()
    assert login_webcam(bio_client, "alice", audio=OTHER_VOICE).status_code == 200
    bio_client.cookies.clear()
    assert login_voice(bio_client, "alice", OTHER_VOICE).status_code == 401  # voice stays its own method


def test_webcam_login_is_locked_after_three_tries(bio_client):
    reg_webcam(bio_client)
    bio_client.cookies.clear()
    codes = [login_webcam(bio_client, video=OTHER_CAM).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_voice_registered_account_cannot_sign_in_by_webcam(bio_client):
    reg_voice(bio_client)
    bio_client.cookies.clear()
    assert (login_webcam(bio_client, video=("c.webm", b"vera-voice-samp")).status_code) == 401


# --- linking ----------------------------------------------------------------------------------


def status_body(**over):
    base = {
        "has_password": True, "google_linked": False, "voice_login": False, "webcam_login": False,
        "has_audio": False, "has_face": False, "require_biometric_2fa": False, "passkey_count": 0, "email_verified": False
    }  # fmt: skip
    return {**base, **over}


def test_link_voice_needs_csrf_login_and_password(bio_client):
    session = register(bio_client)
    files = {"audio": VOICE}
    assert bio_client.post("/auth/me/voice", data=PW, files=files).status_code == 403
    assert bio_client.post("/auth/me/voice", files=files, headers=csrf(session)).status_code == 403
    assert bio_client.post("/auth/me/voice", data={"password": "nope-nope-nope"}, files=files, headers=csrf(session)).status_code == 403
    assert bio_client.post("/auth/me/voice", data=PW, headers=csrf(session)).status_code == 422
    assert bio_client.post("/auth/me/voice", data=PW, files={"audio": BAD}, headers=csrf(session)).status_code == 400
    ok = bio_client.post("/auth/me/voice", data=PW, files=files, headers=csrf(session))
    assert ok.json() == status_body(voice_login=True, has_audio=True)
    bio_client.cookies.clear()
    assert bio_client.post("/auth/me/voice", data=PW, files=files).status_code == 401


def test_link_webcam_and_replace_templates(bio_client):
    session = register(bio_client)
    h = csrf(session)
    assert bio_client.post("/auth/me/webcam", data=PW, files={"video": BAD}, headers=h).status_code == 400
    assert bio_client.post("/auth/me/webcam", data=PW, files={"audio": VOICE}, headers=h).status_code == 422
    ok = bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM, "audio": VOICE}, headers=h)
    assert ok.json() == status_body(webcam_login=True, has_face=True)  # the clip's audio is ignored
    assert bio_client.get("/auth/me").json()["webcam_login"] is True
    bio_client.cookies.clear()
    assert login_webcam(bio_client, "alice").status_code == 200


def test_link_webcam_leaves_the_voice_template_untouched(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=h)
    before = row(bio_client, "alice").audio_embedding
    ok = bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM, "audio": OTHER_VOICE}, headers=h)
    assert ok.json() == status_body(voice_login=True, webcam_login=True, has_audio=True, has_face=True)
    assert row(bio_client, "alice").audio_embedding == before
    bio_client.post("/auth/me/webcam", data=PW, files={"video": OTHER_CAM}, headers=h)  # relink
    assert row(bio_client, "alice").audio_embedding == before


def test_link_voice_and_webcam_without_a_password_needs_no_reauth(gclient):
    session = gclient.post("/auth/google", json={"id_token": "g1|gina@example.com"}).json()
    h = csrf(session)
    assert gclient.post("/auth/me/voice", files={"audio": VOICE}, headers=h).status_code == 200
    ok = gclient.post("/auth/me/webcam", files={"video": CAM}, headers=h)
    assert ok.status_code == 200 and ok.json()["webcam_login"] is True and ok.json()["has_password"] is False


def test_linking_is_throttled_per_user(bio_client):
    session = register(bio_client)
    codes = [
        bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=csrf(session)).status_code
        for _ in range(12)
    ]
    assert codes[0] == 200 and codes[-1] == 429


# --- removal, template cleanup, last-method guard ------------------------------------------------


def remove(c, session, method, data=PW):
    return c.request("DELETE", f"/auth/me/{method}", data=data, headers=csrf(session))


def test_remove_voice_needs_the_password_and_cleans_up(bio_client):
    session = register(bio_client)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=csrf(session))
    assert remove(bio_client, session, "voice", {}).status_code == 403
    assert remove(bio_client, session, "voice", {"password": "wrong-wrong-1"}).status_code == 403
    ok = remove(bio_client, session, "voice")
    assert ok.json() == status_body()
    assert row(bio_client, "alice").audio_embedding is None


def test_remove_voice_leaves_the_face(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM}, headers=h)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=h)
    assert remove(bio_client, session, "voice").json() == status_body(webcam_login=True, has_face=True)
    user = row(bio_client, "alice")
    assert user.audio_embedding is None and user.face_embedding


def test_remove_webcam_deletes_the_face_and_keeps_the_voice(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM}, headers=h)
    assert remove(bio_client, session, "webcam").json() == status_body()
    bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM}, headers=h)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=h)
    assert remove(bio_client, session, "webcam").json() == status_body(voice_login=True, has_audio=True)
    user = row(bio_client, "alice")
    assert user.face_embedding is None and user.audio_embedding


def test_remove_webcam_keeps_an_old_unused_voice_template(bio_client):
    session = register(bio_client)
    cipher = bio_client.app.state.cipher
    with bio_client.app.state.session_factory() as db:  # an account created before the change
        user = db.scalar(select(User).where(User.username == "alice"))
        user.webcam_login = True
        user.face_embedding, user.audio_embedding = cipher.encrypt(b"F:x"), cipher.encrypt(b"A:x")
        db.commit()
    assert remove(bio_client, session, "webcam").json() == status_body(has_audio=True)
    assert row(bio_client, "alice").audio_embedding


def test_second_factor_switches_off_only_when_no_template_remains(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM}, headers=h)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=h)
    bio_client.put("/auth/me/biometric-2fa", data={"enabled": "true", **PW}, headers=h)
    assert remove(bio_client, session, "webcam").json()["require_biometric_2fa"] is True  # voice template remains
    assert remove(bio_client, session, "voice").json()["require_biometric_2fa"] is False


def test_removing_the_last_template_switches_the_second_factor_off(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=h)
    bio_client.put("/auth/me/biometric-2fa", data={"enabled": "true", **PW}, headers=h)
    assert row(bio_client, "alice").biometric_2fa is True
    assert remove(bio_client, session, "voice").json()["require_biometric_2fa"] is False
    assert row(bio_client, "alice").biometric_2fa is False


def test_second_factor_stays_when_a_template_remains(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM}, headers=h)
    bio_client.put("/auth/me/biometric-2fa", data={"enabled": "true", **PW}, headers=h)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=h)
    assert remove(bio_client, session, "voice").json()["require_biometric_2fa"] is True


KEEP = {"detail": "Keep at least one sign-in method"}


def test_cannot_remove_the_only_voice_method(bio_client):
    session = reg_voice(bio_client).json()
    response = remove(bio_client, session, "voice", {})
    assert response.status_code == 409 and response.json() == KEEP
    assert row(bio_client).voice_login is True


def test_cannot_remove_the_only_webcam_method(bio_client):
    session = reg_webcam(bio_client).json()
    response = remove(bio_client, session, "webcam", {})
    assert response.status_code == 409 and response.json() == KEEP
    assert row(bio_client).webcam_login is True


def test_cannot_unlink_the_only_google_method(gclient):
    session = gclient.post("/auth/google", json={"id_token": "g1|gina@example.com"}).json()
    response = gclient.request("DELETE", "/auth/me/google", headers=csrf(session))
    assert response.status_code == 409 and response.json() == KEEP


def test_google_can_be_unlinked_when_voice_or_webcam_remains_and_then_voice_is_last(gclient):
    session = gclient.post("/auth/google", json={"id_token": "g1|gina@example.com"}).json()
    h = csrf(session)
    gclient.post("/auth/me/voice", files={"audio": VOICE}, headers=h)
    assert gclient.request("DELETE", "/auth/me/google", headers=h).status_code == 200
    username = session["username"]
    assert remove(gclient, session, "voice", {}).status_code == 409
    assert row(gclient, username).voice_login is True


def test_each_method_can_go_while_another_remains(gclient):
    session = combined(gclient, data={"password": "correct-horse-battery", "google_id_token": "g1|v@example.com"},
                       voice_audio=VOICE, webcam_video=CAM).json()  # fmt: skip
    pw = {"password": "correct-horse-battery"}
    unlink = gclient.request("DELETE", "/auth/me/google", json=pw, headers=csrf(session))
    assert unlink.status_code == 200
    assert remove(gclient, session, "voice", pw).status_code == 200
    assert remove(gclient, session, "webcam", pw).status_code == 200  # the password remains
    assert flags(row(gclient)) == (True, False, False, False, False, False)


def test_removing_a_method_that_is_off_is_harmless_for_the_guard(bio_client):
    session = reg_voice(bio_client).json()
    assert remove(bio_client, session, "webcam", {}).status_code == 200  # webcam was never on
    assert row(bio_client).voice_login is True


# --- second factor stays an opt-in ---------------------------------------------------------------


def test_second_factor_still_works_end_to_end(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM}, headers=h)
    on = bio_client.put("/auth/me/biometric-2fa", data={"enabled": "true", **PW}, headers=h)
    assert on.json() == status_body(webcam_login=True, has_face=True, require_biometric_2fa=True)
    bio_client.cookies.clear()
    token = bio_client.post("/auth/login", json=CREDS).json()["mfa_token"]
    ok = bio_client.post("/auth/login/biometric", data={"mfa_token": token}, files={"video": CAM})
    assert ok.status_code == 200


def test_second_factor_needs_every_enrolled_template(bio_client):
    session = register(bio_client)
    h = csrf(session)
    bio_client.post("/auth/me/voice", data=PW, files={"audio": VOICE}, headers=h)
    bio_client.post("/auth/me/webcam", data=PW, files={"video": CAM}, headers=h)
    bio_client.put("/auth/me/biometric-2fa", data={"enabled": "true", **PW}, headers=h)
    bio_client.cookies.clear()
    token = bio_client.post("/auth/login", json=CREDS).json()["mfa_token"]
    face_only = bio_client.post("/auth/login/biometric", data={"mfa_token": token}, files={"video": CAM})
    assert face_only.status_code == 401
    both = bio_client.post("/auth/login/biometric", data={"mfa_token": token}, files={"video": CAM, "audio": VOICE})
    assert both.status_code == 200


# --- contract surface -----------------------------------------------------------------------------


def test_openapi_lists_new_routes_and_not_the_removed_ones(bio_client):
    paths = bio_client.get("/openapi.json").json()["paths"]
    for path in ("/auth/register/voice", "/auth/register/webcam", "/auth/register/combined", "/auth/login/voice",
                 "/auth/login/webcam", "/auth/login/biometric", "/auth/me/voice", "/auth/me/webcam",
                 "/auth/me/biometric-2fa"):  # fmt: skip
        assert path in paths, path
    for path in ("/auth/login/biometric-only", "/auth/me/biometrics", "/auth/me/biometric-login"):
        assert path not in paths, path


def test_me_has_the_new_shape(bio_client):
    me = reg_voice(bio_client)
    body = bio_client.get("/auth/me").json()
    assert set(body) == {
        "id", "username", "role", "email", "has_password", "google_linked", "voice_login", "webcam_login",
        "has_audio", "has_face", "require_biometric_2fa", "csrf_token", "passkey_count", "passkeys", "email_verified",
    }  # fmt: skip
    assert me.status_code == 201


def test_body_limit_paths():
    from app.bodylimit import BIOMETRIC_MAX_BYTES, DEFAULT_MAX_BYTES, limit_for

    big = ("/auth/login/voice", "/auth/login/webcam", "/auth/login/biometric", "/auth/register/voice",
           "/auth/register/webcam", "/auth/register/combined", "/auth/me/voice", "/auth/me/webcam")  # fmt: skip
    for path in big:
        assert limit_for(path, True) == BIOMETRIC_MAX_BYTES and limit_for(path, False) == DEFAULT_MAX_BYTES
    for path in ("/auth/login", "/auth/register", "/auth/me/password", "/auth/login/biometric-only", "/auth/me/biometrics"):
        assert limit_for(path, True) == DEFAULT_MAX_BYTES
