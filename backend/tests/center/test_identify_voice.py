"""Voice sign-in without a username (1-N), voice uniqueness, optional username, real-engine helpers."""

import logging
import struct

import pytest
from sqlalchemy import func, select

from api.center.biometrics import RealBiometrics
from api.center.config import Settings
from api.center.identify import DUMMY_FACE, DUMMY_VOICE, identify_voice
from api.center.models import User
from tests.center.fakes import fake_google_verifier
from tests.center.helpers import csrf
from tests.center.test_signin_methods import COOKIES, cookie_names, login_voice, reg_voice, row

FAILED = (401, '{"detail":"Biometric login failed"}')
PW = {"password": "Correct-Horse-Battery1"}


def voice(value: float, who: str) -> tuple[str, bytes]:
    """Fake voice = `value`; similarity between two voices is 1 - |a - b|."""
    return ("v.webm", f"v{value:.2f}-{who}".encode())


ANA, BEN, CLEO = voice(0.0, "ana"), voice(0.5, "ben"), voice(1.0, "cleo")


def _post(c, audio, data=None):
    return c.post("/auth/login/voice", data=data or {}, files={"audio": audio} if audio else None)


def shape(response):
    return response.status_code, response.text


def enroll(c, name, audio):
    assert reg_voice(c, name, audio).status_code == 201, name
    c.cookies.clear()


@pytest.fixture
def three(bio_client):
    for name, audio in (("ana", ANA), ("ben", BEN), ("cleo", CLEO)):
        enroll(bio_client, name, audio)
    return bio_client


def add_voice_user(c, username, embedding: bytes, **extra):
    with c.app.state.session_factory() as db:
        db.add(User(username=username, password_hash="!", voice_login=True,
                    audio_embedding=c.app.state.cipher.encrypt(embedding), **extra))  # fmt: skip
        db.commit()


# --- identification ---------------------------------------------------------------------------


def test_identifies_a_single_account(bio_client):
    enroll(bio_client, "ana", ANA)
    response = _post(bio_client, ANA)
    assert response.status_code == 200 and response.json()["username"] == "ana"
    assert cookie_names(response) == COOKIES


def test_picks_the_right_account_among_several(three):
    for name, audio in (("cleo", CLEO), ("ana", ANA), ("ben", BEN)):
        response = _post(three, audio)
        assert response.status_code == 200 and response.json()["username"] == name
        three.cookies.clear()


def test_near_voice_signs_in(three):
    assert _post(three, voice(0.05, "x")).json()["username"] == "ana"


def test_below_threshold_is_rejected(three):
    assert shape(_post(three, voice(0.2, "x"))) == FAILED  # similarity 0.8 to ana, under 0.88


def test_ambiguous_match_is_rejected_and_margin_is_configurable(bio_client):
    enroll(bio_client, "ana", ANA)
    add_voice_user(bio_client, "twin", b"A:v0.03-twin")  # similarity gap 0.03 < 0.05
    assert shape(_post(bio_client, ANA)) == FAILED
    object.__setattr__(bio_client.app.state.settings, "voice_identify_margin", 0.01)
    assert _post(bio_client, ANA).json()["username"] == "ana"


def test_unknown_voice_and_no_candidates(bio_client):
    assert shape(_post(bio_client, ANA)) == FAILED  # nobody enrolled
    enroll(bio_client, "ana", ANA)
    assert shape(_post(bio_client, voice(9.0, "stranger"))) == FAILED


def test_identical_401s_across_failure_types(three):
    responses = [
        _post(three, voice(0.2, "x")),
        _post(three, voice(9.0, "x")),
        _post(three, ("b.webm", b"bad-recording")),
        _post(three, None),
    ]
    for response in responses:
        assert shape(response) == FAILED and "set-cookie" not in response.headers


def test_method_not_enabled_is_the_same_401(bio_client):
    enroll(bio_client, "ana", ANA)
    with bio_client.app.state.session_factory() as db:
        db.scalar(select(User).where(func.lower(User.username) == "ana")).voice_login = False
        db.commit()
    assert shape(_post(bio_client, ANA)) == FAILED


def test_no_candidate_does_one_dummy_comparison(bio_client, monkeypatch):
    calls = []
    engine = bio_client.app.state.biometrics
    original = engine.audio_similarity
    monkeypatch.setattr(engine, "audio_similarity", lambda a, b: calls.append(a) or original(a, b))
    assert shape(_post(bio_client, ANA)) == FAILED
    assert calls == [DUMMY_VOICE]


def test_zero_candidates_with_the_real_engine_does_not_crash(bio_client):
    class Request:
        class app:  # noqa: N801
            class state:  # noqa: N801
                biometrics = RealBiometrics(Settings.from_env())
                cipher = bio_client.app.state.cipher
                settings = bio_client.app.state.settings

    with bio_client.app.state.session_factory() as db:
        assert identify_voice(Request, db, bytes(1024)) is None
        assert identify_voice(Request, db, DUMMY_VOICE) is None


def test_username_given_path_unchanged(three):
    assert login_voice(three, "ana", ANA).status_code == 200
    three.cookies.clear()
    assert shape(login_voice(three, "ana", BEN)) == FAILED
    assert shape(login_voice(three, "ghost", ANA)) == FAILED
    assert _post(three, ANA, data={"username": "  "}).status_code == 200  # blank = identification


# --- throttles and cap ------------------------------------------------------------------------


def test_per_ip_throttle_is_separate_from_the_face_counters(three):
    for _ in range(5):
        assert _post(three, voice(9.0, "x")).status_code == 401
    blocked = _post(three, ANA)
    assert blocked.status_code == 429 and "Too many attempts" in blocked.text
    assert not three.app.state.identify_ip_throttle.is_blocked("testclient")
    assert three.post("/auth/login/webcam", files={"video": ("c.webm", b"x")}).status_code == 401


def test_global_throttle_is_separate(three):
    glob = three.app.state.voice_identify_global_throttle
    for _ in range(100):
        glob.record("all")
    assert _post(three, ANA).status_code == 429
    assert not three.app.state.identify_global_throttle.is_blocked("all")


def test_success_clears_the_ip_counter(three):
    assert _post(three, voice(9.0, "x")).status_code == 401
    assert _post(three, ANA).status_code == 200
    assert three.app.state.voice_identify_ip_throttle.tracked_keys() == 0


def test_candidate_cap_asks_for_a_username(three, monkeypatch):
    monkeypatch.setattr("api.center.identify.MAX_IDENTIFY_CANDIDATES", 2)
    response = _post(three, ANA)
    assert response.status_code == 422 and response.json()["detail"] == "Enter your username"
    assert login_voice(three, "ana", ANA).status_code == 200


def test_audit_log_has_no_vectors_or_guessed_names(three, caplog):
    caplog.set_level(logging.INFO, logger="auth.audit")
    _post(three, voice(9.0, "mallory"))
    _post(three, ANA)
    text = caplog.text
    assert "voice identify failed ip=testclient" in text and "login ok (voice identify)" in text
    assert "A:" not in text and "mallory" not in text
    failed = [r.getMessage() for r in caplog.records if "failed" in r.getMessage()]
    assert failed and all("user=" not in m for m in failed)


# --- uniqueness -------------------------------------------------------------------------------


def test_duplicate_voice_rejected_on_register_voice(bio_client):
    enroll(bio_client, "ana", ANA)
    response = reg_voice(bio_client, "dupe", voice(0.05, "dupe"))
    assert response.status_code == 409 and response.json()["detail"] == "This voice is already registered"
    assert row(bio_client, "dupe") is None
    assert reg_voice(bio_client, "benny", BEN).status_code == 201


def test_duplicate_voice_rejected_on_combined(bio_client):
    enroll(bio_client, "ana", ANA)
    response = bio_client.post(
        "/auth/register/combined", data={"username": "dupe", **PW}, files={"voice_audio": voice(0.02, "d")}
    )
    assert response.status_code == 409 and row(bio_client, "dupe") is None


def test_me_voice_duplicate_rejected_and_relinking_own_voice_allowed(bio_client):
    enroll(bio_client, "ana", ANA)
    session = bio_client.post("/auth/register/combined", data={"username": "benny", **PW}).json()
    dup = bio_client.post("/auth/me/voice", data=PW, files={"audio": voice(0.1, "x")}, headers=csrf(session))
    assert dup.status_code == 409 and row(bio_client, "benny").voice_login is False
    ok = bio_client.post("/auth/me/voice", data=PW, files={"audio": BEN}, headers=csrf(session))
    assert ok.status_code == 200
    again = bio_client.post("/auth/me/voice", data=PW, files={"audio": voice(0.52, "b")}, headers=csrf(session))
    assert again.status_code == 200


def test_uniqueness_check_skipped_above_the_cap(bio_client, monkeypatch, caplog):
    enroll(bio_client, "ana", ANA)
    monkeypatch.setattr("api.center.identify.MAX_IDENTIFY_CANDIDATES", 0)
    with caplog.at_level(logging.WARNING, logger="auth.audit"):
        assert reg_voice(bio_client, "dupe", voice(0.02, "d")).status_code == 201
    assert "uniqueness check skipped" in caplog.text


# --- optional username ------------------------------------------------------------------------


def combined_nameless(c, data=None, **files):
    return c.post("/auth/register/combined", data=data or {}, files=files or None)


def test_voice_only_gets_a_generated_handle_and_signs_in_without_it(bio_client):
    response = combined_nameless(bio_client, voice_audio=ANA)
    assert response.status_code == 201
    name = response.json()["username"]
    assert name.startswith("user-") and len(name) == 11 and row(bio_client, name).voice_login is True
    bio_client.cookies.clear()
    assert _post(bio_client, ANA).json()["username"] == name


def test_register_voice_endpoint_without_a_username(bio_client):
    response = bio_client.post("/auth/register/voice", files={"audio": ANA})
    assert response.status_code == 201 and response.json()["username"].startswith("user-")


def test_voice_and_webcam_without_a_name(bio_client):
    response = combined_nameless(bio_client, voice_audio=ANA, webcam_video=("c.webm", b"f0.00-a"))
    assert response.status_code == 201 and response.json()["username"].startswith("user-")


def test_voice_and_google_without_a_name_uses_the_email_handle(bio_client):
    bio_client.app.state.google_verifier = fake_google_verifier
    response = combined_nameless(bio_client, data={"google_id_token": "s9|kim@example.com"}, voice_audio=ANA)
    assert response.status_code == 201 and response.json()["username"] == "kim"


def test_voice_and_password_without_a_name_is_422(bio_client):
    response = combined_nameless(bio_client, data=PW, voice_audio=ANA)
    assert response.status_code == 422 and response.json()["detail"] == "Choose a username"
    with bio_client.app.state.session_factory() as db:
        assert db.scalar(select(User.id)) is None


# --- the REAL engine never raises on odd data -------------------------------------------------


def real():
    return RealBiometrics(Settings.from_env())


def floats(*values: float) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


@pytest.mark.parametrize(
    "stored,probe",
    [
        (b"A:" + bytes(17), bytes(1024)),
        (bytes(1024), bytes(1024)),
        (DUMMY_VOICE, bytes(512)),
        (b"", b""),
        (bytes(1024), b"A:" + bytes(17)),
        (floats(float("nan"), 1.0), floats(1.0, 1.0)),
    ],
)
def test_audio_similarity_never_raises_and_is_minus_one(stored, probe):
    assert real().audio_similarity(stored, probe) == -1.0
    assert real().audio_matches(stored, probe) is False
    assert real().audio_matches(stored, probe, strict=True) is False


def test_audio_similarity_of_real_vectors():
    assert real().audio_similarity(floats(1, 0), floats(2, 0)) == pytest.approx(1.0)
    assert real().audio_similarity(floats(1, 0), floats(0, 1)) == pytest.approx(0.0)
    assert real().audio_similarity(DUMMY_VOICE, DUMMY_VOICE) == pytest.approx(1.0)


def test_face_distance_with_malformed_and_placeholder_inputs():
    assert real().face_distance(b"", b"") == float("inf")
    assert real().face_distance(b"F:" + bytes(17), bytes(512)) == float("inf")
    assert real().face_distance(DUMMY_FACE, bytes(512)) == 0.0
    assert real().face_distance(DUMMY_FACE, bytes(1024)) == float("inf")


def test_voice_placeholder_is_well_formed_with_a_non_zero_norm():
    assert len(DUMMY_VOICE) == 256 * 4 and any(DUMMY_VOICE)
