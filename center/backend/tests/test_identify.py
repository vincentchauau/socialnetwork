"""Webcam sign-in without a username (1-N), face uniqueness, optional username at registration."""

import logging

import pytest
from sqlalchemy import select

from app.models import User
from tests.fakes import fake_google_verifier
from tests.helpers import csrf
from tests.test_signin_methods import (
    COOKIES,
    cookie_names,
    login_webcam,
    reg_webcam,
    row,
)

FAILED = (401, '{"detail":"Biometric login failed"}')


def clip(face: float, who: str) -> tuple[str, bytes]:
    """Fake face = `face`, fake voice = `who` (both derive from the first 16 bytes of the clip)."""
    return ("c.webm", f"f{face:.2f}-{who}".encode())


ALICE, BOB, CAROL = clip(0.0, "alice"), clip(1.0, "bob"), clip(2.0, "carol")


def _post(c, video, audio=None, data=None):
    files = {**({"video": video} if video else {}), **({"audio": audio} if audio else {})}
    return c.post("/auth/login/webcam", data=data or {}, files=files or None)


def enroll(c, name, video):
    assert reg_webcam(c, name, video).status_code == 201, name
    c.cookies.clear()


@pytest.fixture
def three(bio_client):
    for name, video in (("alice", ALICE), ("bob", BOB), ("carol", CAROL)):
        enroll(bio_client, name, video)
    return bio_client


def shape(response):
    return response.status_code, response.text


# --- identification ---------------------------------------------------------------------------


def test_identifies_a_single_account(bio_client):
    enroll(bio_client, "alice", ALICE)
    response = _post(bio_client, ALICE)
    assert response.status_code == 200 and response.json()["username"] == "alice"
    assert cookie_names(response) == COOKIES


def test_identifies_the_right_account_among_several(three):
    for name, video in (("carol", CAROL), ("alice", ALICE), ("bob", BOB)):
        response = _post(three, video)
        assert response.status_code == 200 and response.json()["username"] == name
        three.cookies.clear()


def test_near_face_with_the_same_voice_signs_in(three):
    # the voice template is alice's clip prefix; a separate audio file supplies the same voice
    response = _post(three, ("c.webm", b"f0.30-zzz"), audio=("a.webm", b"f0.00-alice"))
    assert response.status_code == 200 and response.json()["username"] == "alice"


def test_failures_are_identical_401s(three):
    wrong_face = _post(three, clip(5.0, "alice"))
    wrong_voice = _post(three, clip(0.0, "mallory"))
    unusable = _post(three, ("b.webm", b"bad-clip"))
    silent = _post(three, ("c.webm", b"f0.00-silent"))
    no_clip = _post(three, None)
    for response in (wrong_face, wrong_voice, unusable, silent, no_clip):
        assert shape(response) == FAILED
        assert "set-cookie" not in response.headers


def test_no_candidates_is_the_same_401(bio_client):
    assert shape(_post(bio_client, ALICE)) == FAILED


def test_method_not_enabled_is_the_same_401(bio_client):
    enroll(bio_client, "alice", ALICE)
    with bio_client.app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        user.webcam_login = False
        db.commit()
    assert shape(_post(bio_client, ALICE)) == FAILED


def test_ambiguous_best_match_is_rejected(bio_client):
    enroll(bio_client, "alice", ALICE)
    # a second, near-identical face can only exist if built directly in the database
    cipher = bio_client.app.state.cipher
    with bio_client.app.state.session_factory() as db:
        twin = User(
            username="twin", password_hash="!", webcam_login=True,
            face_embedding=cipher.encrypt(b"F:f0.02-alice"), audio_embedding=cipher.encrypt(b"A:f0.00-alice"),
        )  # fmt: skip
        db.add(twin)
        db.commit()
    assert shape(_post(bio_client, ALICE)) == FAILED


def test_margin_is_configurable(bio_client, monkeypatch):
    enroll(bio_client, "alice", ALICE)
    cipher = bio_client.app.state.cipher
    with bio_client.app.state.session_factory() as db:
        db.add(User(
            username="twin", password_hash="!", webcam_login=True,
            face_embedding=cipher.encrypt(b"F:f0.02-alice"), audio_embedding=cipher.encrypt(b"A:f0.00-alice"),
        ))  # fmt: skip
        db.commit()
    settings = bio_client.app.state.settings
    object.__setattr__(settings, "face_identify_margin", 0.01)
    assert _post(bio_client, ALICE).json()["username"] == "alice"


def test_voice_mismatch_counts_against_that_account_and_locks_only_webcam(three):
    for _ in range(5):
        assert shape(_post(three, clip(0.0, "mallory"))) == FAILED
        three.app.state.identify_ip_throttle.reset("testclient")
    # alice's webcam is locked even for the real owner (identical 401, nothing revealed)
    assert shape(_post(three, ALICE)) == FAILED
    three.app.state.identify_ip_throttle.reset("testclient")
    assert _post(three, BOB).status_code == 200  # other accounts unaffected
    # username path also respects the lock
    three.cookies.clear()
    assert login_webcam(three, "alice", ALICE).status_code == 429


def test_account_lock_does_not_touch_other_methods(three):
    three.app.state.webcam_account_throttle.record("alice")
    assert row(three, "alice").webcam_login is True
    assert three.app.state.alone_account_throttle.is_blocked("alice") is False


def test_success_clears_ip_and_account_counters(three):
    assert shape(_post(three, clip(0.0, "mallory"))) == FAILED
    assert _post(three, ALICE).status_code == 200
    state = three.app.state
    assert not state.identify_ip_throttle.is_blocked("testclient")
    assert state.webcam_account_throttle.tracked_keys() == 0


def test_unknown_face_does_not_touch_account_throttles(three):
    assert shape(_post(three, clip(9.0, "alice"))) == FAILED
    assert three.app.state.webcam_account_throttle.tracked_keys() == 0


# --- throttles and cap ------------------------------------------------------------------------


def test_per_ip_throttle(three):
    for _ in range(5):
        assert _post(three, clip(9.0, "x")).status_code == 401
    blocked = _post(three, ALICE)
    assert blocked.status_code == 429 and "Too many attempts" in blocked.text


def test_global_throttle(three):
    glob = three.app.state.identify_global_throttle
    for _ in range(100):
        glob.record("all")
    assert _post(three, ALICE).status_code == 429


def test_candidate_cap_asks_for_a_username(three, monkeypatch):
    monkeypatch.setattr("app.identify.MAX_IDENTIFY_CANDIDATES", 2)
    response = _post(three, ALICE)
    assert response.status_code == 422 and response.json()["detail"] == "Enter your username"
    assert login_webcam(three, "alice", ALICE).status_code == 200  # username path unaffected


def test_username_given_path_unchanged(three):
    assert login_webcam(three, "alice", ALICE).status_code == 200
    three.cookies.clear()
    assert shape(login_webcam(three, "alice", BOB)) == FAILED
    assert shape(login_webcam(three, "ghost", ALICE)) == FAILED
    assert _post(three, ALICE, data={"username": "  "}).status_code == 200  # blank = identification


def test_audit_log_has_no_vectors_or_guessed_names(three, caplog):
    caplog.set_level(logging.INFO, logger="auth.audit")
    _post(three, clip(0.0, "mallory"))
    _post(three, ALICE)
    text = caplog.text
    assert "webcam identify failed ip=testclient" in text and "login ok (webcam identify)" in text
    assert "F:" not in text and "A:" not in text and "mallory" not in text
    failed = [r.getMessage() for r in caplog.records if "failed" in r.getMessage()]
    assert failed and all("user=" not in m and "alice" not in m for m in failed)


# --- registration keeps faces unambiguous -----------------------------------------------------


def test_duplicate_face_rejected_on_register_webcam(bio_client):
    enroll(bio_client, "alice", ALICE)
    response = reg_webcam(bio_client, "dupe", clip(0.3, "dupe"))
    assert response.status_code == 409 and response.json()["detail"] == "This face is already registered"
    assert row(bio_client, "dupe") is None
    assert reg_webcam(bio_client, "bobby", BOB).status_code == 201


def test_duplicate_face_rejected_on_combined_without_creating_anything(bio_client):
    enroll(bio_client, "alice", ALICE)
    response = bio_client.post(
        "/auth/register/combined", data={"username": "dupe", "password": "correct-horse-battery"},
        files={"webcam_video": clip(0.1, "dupe")},
    )
    assert response.status_code == 409 and row(bio_client, "dupe") is None


def test_me_webcam_duplicate_rejected_and_own_face_relink_allowed(bio_client):
    enroll(bio_client, "alice", ALICE)
    r = bio_client.post("/auth/register/combined", data={"username": "bobby", "password": "correct-horse-battery"})
    assert r.status_code == 201
    session = r.json()
    pw = {"password": "correct-horse-battery"}
    dup = bio_client.post("/auth/me/webcam", data=pw, files={"video": clip(0.2, "x")}, headers=csrf(session))
    assert dup.status_code == 409 and row(bio_client, "bobby").webcam_login is False
    ok = bio_client.post("/auth/me/webcam", data=pw, files={"video": BOB}, headers=csrf(session))
    assert ok.status_code == 200
    again = bio_client.post("/auth/me/webcam", data=pw, files={"video": clip(1.1, "bob")}, headers=csrf(session))
    assert again.status_code == 200  # re-linking near her own previous face is fine


def test_uniqueness_check_skipped_above_the_cap(bio_client, monkeypatch, caplog):
    enroll(bio_client, "alice", ALICE)
    monkeypatch.setattr("app.identify.MAX_IDENTIFY_CANDIDATES", 0)
    with caplog.at_level(logging.WARNING, logger="auth.audit"):
        assert reg_webcam(bio_client, "dupe", clip(0.1, "dupe")).status_code == 201
    assert "uniqueness check skipped" in caplog.text


# --- optional username ------------------------------------------------------------------------


def combined_nameless(c, data=None, **files):
    return c.post("/auth/register/combined", data=data or {}, files=files or None)


def test_webcam_only_gets_a_generated_handle(bio_client):
    response = combined_nameless(bio_client, webcam_video=ALICE)
    assert response.status_code == 201
    name = response.json()["username"]
    assert name.startswith("user-") and len(name) == 11
    assert row(bio_client, name).email is None
    bio_client.cookies.clear()
    assert _post(bio_client, ALICE).json()["username"] == name


def test_generated_handle_retries_on_collision(bio_client, monkeypatch):
    values = iter(["aaaaaa", "aaaaaa", "bbbbbb"])
    monkeypatch.setattr("app.routes_methods.secrets.token_hex", lambda n: next(values))
    assert combined_nameless(bio_client, webcam_video=ALICE).json()["username"] == "user-aaaaaa"
    bio_client.cookies.clear()
    assert combined_nameless(bio_client, webcam_video=BOB).json()["username"] == "user-bbbbbb"


def test_google_only_uses_the_email_handle(bio_client):
    bio_client.app.state.google_verifier = fake_google_verifier
    response = combined_nameless(bio_client, data={"google_id_token": "sub1|jane.doe@example.com"})
    assert response.status_code == 201 and response.json()["username"] == "jane.doe"


def test_google_and_webcam_without_a_name_uses_the_email_handle(bio_client):
    bio_client.app.state.google_verifier = fake_google_verifier
    response = combined_nameless(
        bio_client, data={"google_id_token": "sub2|kim@example.com"}, webcam_video=ALICE
    )
    assert response.status_code == 201 and response.json()["username"] == "kim"
    assert row(bio_client, "kim").webcam_login is True


@pytest.mark.parametrize(
    "data,files",
    [
        ({"password": "correct-horse-battery"}, {}),
        ({"password": "correct-horse-battery"}, {"webcam_video": ALICE}),
        ({}, {"voice_audio": ("v.webm", b"vera-voice")}),
        ({}, {"voice_audio": ("v.webm", b"vera-voice"), "webcam_video": ALICE}),
        ({"username": "  ", "password": "correct-horse-battery"}, {}),
    ],
)
def test_username_required_for_password_and_voice(bio_client, data, files):
    response = combined_nameless(bio_client, data=data, **files)
    assert response.status_code == 422 and response.json()["detail"] == "Choose a username"
    with bio_client.app.state.session_factory() as db:
        assert db.scalar(select(User.id)) is None


def test_nothing_chosen_is_still_the_no_method_error(bio_client):
    response = combined_nameless(bio_client)
    assert response.status_code == 422 and "at least one" in response.json()["detail"]


def test_explicit_usernames_behave_as_before(bio_client):
    response = bio_client.post(
        "/auth/register/combined", data={"username": "Zed"}, files={"webcam_video": ALICE}
    )
    assert response.status_code == 201 and response.json()["username"] == "zed"
