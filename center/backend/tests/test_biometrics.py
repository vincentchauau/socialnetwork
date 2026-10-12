import threading

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.biometrics import RealBiometrics
from app.config import ConfigError, Settings
from app.crypto import TemplateCipher
from app.main import create_app
from app.models import User
from app.tokens import create_mfa_token
from tests.fakes import FakeBiometrics
from tests.helpers import CREDS, csrf, register

PW = {"password": CREDS["password"]}
VOICE = ("voice.webm", b"alice-voice-sample")
FACE = ("face.webm", b"alice-face-sample")


def files(audio=None, video=None):
    out = {}
    if audio is not None:
        out["audio"] = audio
    if video is not None:
        out["video"] = video
    return out


def enroll(client, session, audio=VOICE, video=FACE, data=None):
    return client.post(
        "/auth/me/biometrics", data=data or PW, files=files(audio, video), headers=csrf(session)
    )


@pytest.fixture
def enrolled(bio_client):
    """Alice with voice (from the audio file) and face enrolled, then signed out."""
    session = register(bio_client)
    assert enroll(bio_client, session).status_code == 200
    bio_client.cookies.clear()
    return bio_client


def mfa_token(client):
    body = client.post("/auth/login", json=CREDS).json()
    assert body["mfa_required"] is True
    return body["mfa_token"]


# --- feature flag -----------------------------------------------------------------------------


def test_disabled_by_default_every_route_is_503(client):
    session = register(client)
    attempts = [
        client.post("/auth/login/biometric", data={"mfa_token": "x"}),
        client.post("/auth/login/biometric-only", data={"username": "alice"}),
        client.post("/auth/me/biometrics", data=PW, headers=csrf(session)),
        client.put("/auth/me/biometric-login", data={"enabled": "true", **PW}, headers=csrf(session)),
        client.request("DELETE", "/auth/me/biometrics", data=PW, headers=csrf(session)),
    ]
    assert [r.status_code for r in attempts] == [503] * 5
    assert attempts[0].json() == {"detail": "Biometrics are not available"}
    assert client.get("/auth/config").json()["biometrics_enabled"] is False


def test_enabled_flag_shows_in_config(bio_client):
    assert bio_client.get("/auth/config").json()["biometrics_enabled"] is True


def test_enabling_without_data_key_fails_at_startup(monkeypatch):
    monkeypatch.setenv("BIOMETRICS_ENABLED", "1")
    with pytest.raises(ConfigError, match="DATA_KEY"):
        create_app("sqlite://")


def test_invalid_data_key_fails_at_startup(monkeypatch):
    monkeypatch.setenv("BIOMETRICS_ENABLED", "1")
    monkeypatch.setenv("DATA_KEY", "not-a-fernet-key")
    with pytest.raises(ConfigError, match="Fernet"):
        create_app("sqlite://")


def test_real_engine_without_libraries_reports_503_not_500(monkeypatch):
    monkeypatch.setenv("BIOMETRICS_ENABLED", "1")
    monkeypatch.setenv("DATA_KEY", Fernet.generate_key().decode())
    client = TestClient(create_app("sqlite://"))  # real engine, heavy libs absent or without ffmpeg
    session = register(client)
    response = enroll(client, session, audio=("a.webm", b"not really audio"), video=None)
    assert response.status_code in (400, 503)  # unusable sample or missing lib, never a crash


# --- enrollment management --------------------------------------------------------------------


def test_enroll_stores_encrypted_templates_and_reports_state(bio_client):
    session = register(bio_client)
    response = enroll(bio_client, session)
    assert response.json() == {"has_audio": True, "has_face": True, "biometric_login": False}
    me = bio_client.get("/auth/me").json()
    assert (me["has_audio"], me["has_face"]) == (True, True)
    with bio_client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert b"alice-voice" not in user.audio_embedding and b"alice-face" not in user.face_embedding
        assert bio_client.app.state.cipher.decrypt(user.audio_embedding) == b"A:alice-voice-samp"


def test_enroll_voice_is_taken_from_the_video_when_no_audio_is_sent(bio_client):
    session = register(bio_client)
    response = enroll(bio_client, session, audio=None)
    assert response.json()["has_audio"] is True and response.json()["has_face"] is True


def test_enroll_with_a_silent_video_yields_face_only(bio_client):
    session = register(bio_client)
    response = enroll(bio_client, session, audio=None, video=("v.webm", b"silent-video"))
    assert (response.json()["has_audio"], response.json()["has_face"]) == (False, True)


def test_enroll_only_replaces_the_samples_that_were_sent(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    state = enroll(bio_client, session, audio=("v2.webm", b"another-voice"), video=None).json()
    assert state["has_face"] is True and state["has_audio"] is True


def test_enroll_rules(bio_client):
    session = register(bio_client)
    assert bio_client.post("/auth/me/biometrics", data=PW, files=files(VOICE)).status_code == 403  # csrf
    assert enroll(bio_client, session, data={"password": "wrong-password"}).status_code == 403
    assert enroll(bio_client, session, audio=None, video=None).status_code == 422
    assert enroll(bio_client, session, audio=("a.webm", b"bad-audio"), video=None).status_code == 400
    big = ("a.webm", b"x" * 3_000_001)
    assert enroll(bio_client, session, audio=big, video=None).status_code == 413


def test_enroll_is_throttled_per_user(bio_client):
    session = register(bio_client)
    codes = [enroll(bio_client, session).status_code for _ in range(12)]
    assert codes[0] == 200 and codes[-1] == 429


def test_unavailable_engine_is_503_without_details(bio_client):
    session = register(bio_client)
    response = enroll(bio_client, session, audio=("a.webm", b"missing-lib"), video=None)
    assert response.status_code == 503
    assert "ffmpeg" not in response.text


def test_biometric_login_opt_in_needs_both_samples(bio_client):
    session = register(bio_client)
    on = {"enabled": "true", **PW}
    assert bio_client.put("/auth/me/biometric-login", data=on, headers=csrf(session)).status_code == 422
    enroll(bio_client, session, audio=None, video=("v.webm", b"silent-video"))
    assert bio_client.put("/auth/me/biometric-login", data=on, headers=csrf(session)).status_code == 422
    enroll(bio_client, session)
    assert bio_client.put("/auth/me/biometric-login", data={"enabled": "true"}, headers=csrf(session)).status_code == 403
    ok = bio_client.put("/auth/me/biometric-login", data=on, headers=csrf(session))
    assert ok.json()["biometric_login"] is True
    assert bio_client.get("/auth/me").json()["biometric_login"] is True


def test_delete_biometrics_clears_everything_and_disables_biometric_login(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    bio_client.put("/auth/me/biometric-login", data={"enabled": "true", **PW}, headers=csrf(session))
    assert bio_client.request("DELETE", "/auth/me/biometrics", headers=csrf(session)).status_code == 403
    response = bio_client.request("DELETE", "/auth/me/biometrics", data=PW, headers=csrf(session))
    assert response.json() == {"has_audio": False, "has_face": False, "biometric_login": False}
    bio_client.cookies.clear()
    assert bio_client.post("/auth/login", json=CREDS).json().get("mfa_required") is None


# --- second factor ----------------------------------------------------------------------------


def test_password_login_returns_an_mfa_challenge_without_cookies(enrolled):
    response = enrolled.post("/auth/login", json=CREDS)
    body = response.json()
    assert set(body) == {"mfa_required", "mfa_token"} and body["mfa_required"] is True
    assert "set-cookie" not in response.headers
    assert enrolled.get("/auth/me").status_code == 401


def test_mfa_with_matching_samples_issues_a_session(enrolled):
    response = enrolled.post(
        "/auth/login/biometric", data={"mfa_token": mfa_token(enrolled)}, files=files(VOICE, FACE)
    )
    assert response.status_code == 200
    assert response.json()["username"] == "alice" and response.json()["csrf_token"]
    assert enrolled.get("/auth/me").status_code == 200
    assert set(c.split("=")[0] for c in response.headers.get_list("set-cookie")) == {"sn_token", "sn_refresh"}


def test_mfa_needs_every_enrolled_factor_even_when_the_voice_matches_via_video(enrolled):
    video = ("v.webm", b"alice-voice-sample")  # fake engine derives both embeddings from the same bytes
    response = enrolled.post("/auth/login/biometric", data={"mfa_token": mfa_token(enrolled)}, files=files(None, video))
    assert response.status_code == 401  # face differs (F: vs stored face sample): every factor must match


@pytest.mark.parametrize(
    "probe",
    [
        files(("a.webm", b"someone-else-voice"), FACE),  # wrong voice
        files(VOICE, ("v.webm", b"someone-else-face")),  # wrong face
        files(VOICE, None),  # missing face
        files(None, FACE),  # missing voice (video has no usable audio is not guaranteed; fake derives A: from FACE)
        {},  # nothing at all
        files(("a.webm", b"bad"), FACE),  # unusable sample
    ],
)
def test_mfa_rejects_wrong_or_missing_samples(enrolled, probe):
    response = enrolled.post("/auth/login/biometric", data={"mfa_token": mfa_token(enrolled)}, files=probe or None)
    assert response.status_code == 401
    assert response.json()["detail"] == "Biometric verification failed"
    assert enrolled.get("/auth/me").status_code == 401


def test_mfa_token_must_be_valid_unexpired_and_typed(enrolled):
    from tests.helpers import forge
    import time

    good = mfa_token(enrolled)
    uid = enrolled.app.state.session_factory().scalar(select(User.id))
    candidates = [
        good[:-3] + "abc",
        "garbage",
        forge({"sub": str(uid), "typ": "mfa", "ver": 0, "exp": int(time.time()) - 1}),
        forge({"sub": str(uid), "typ": "refresh", "ver": 0}),
        forge({"sub": str(uid), "typ": "mfa", "ver": 0}, secret="z" * 40),
        forge({"sub": str(uid), "typ": "mfa", "ver": 7}),  # revoked: ver no longer matches
        create_mfa_token(9999, 0),  # user gone
    ]
    for token in candidates:
        r = enrolled.post("/auth/login/biometric", data={"mfa_token": token}, files=files(VOICE, FACE))
        assert r.status_code == 401, token
        assert r.json()["detail"] == "Invalid or expired login session"


def test_mfa_failures_are_throttled_per_user_and_ip(enrolled):
    token = mfa_token(enrolled)
    wrong = files(("a.webm", b"nope"), FACE)
    codes = [enrolled.post("/auth/login/biometric", data={"mfa_token": token}, files=wrong).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    # Even the right sample is refused while locked.
    assert enrolled.post("/auth/login/biometric", data={"mfa_token": token}, files=files(VOICE, FACE)).status_code == 429


def test_mfa_success_resets_the_counter(enrolled):
    token = mfa_token(enrolled)
    wrong = files(("a.webm", b"nope"), FACE)
    for _ in range(4):
        enrolled.post("/auth/login/biometric", data={"mfa_token": token}, files=wrong)
    assert enrolled.post("/auth/login/biometric", data={"mfa_token": token}, files=files(VOICE, FACE)).status_code == 200
    for _ in range(4):
        assert enrolled.post("/auth/login/biometric", data={"mfa_token": token}, files=wrong).status_code == 401


def test_google_login_of_an_enrolled_account_also_needs_the_second_factor(bio_client):
    from tests.fakes import fake_google_verifier

    bio_client.app.state.google_verifier = fake_google_verifier
    session = bio_client.post("/auth/google", json={"id_token": "g1|gina@example.com"}).json()
    assert enroll(bio_client, session, data={}).status_code == 200  # Google-only: no password to confirm
    bio_client.cookies.clear()
    body = bio_client.post("/auth/google", json={"id_token": "g1|gina@example.com"}).json()
    assert body["mfa_required"] is True


# --- biometric-only login ----------------------------------------------------------------------


def opt_in(client, session):
    client.put("/auth/me/biometric-login", data={"enabled": "true", **PW}, headers=csrf(session))


def alone(client, username="alice", audio=VOICE, video=FACE):
    return client.post("/auth/login/biometric-only", data={"username": username}, files=files(audio, video))


def test_biometric_only_login_for_opted_in_accounts(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    opt_in(bio_client, session)
    bio_client.cookies.clear()

    response = alone(bio_client, "ALICE")

    assert response.status_code == 200 and response.json()["username"] == "alice"
    assert bio_client.get("/auth/me").status_code == 200
    assert True in bio_client.app.state.biometrics.strict_calls  # strict thresholds were used


def test_biometric_only_every_failure_is_the_same_401(bio_client):
    register(bio_client, {"username": "nobio", "password": "s3cret-pass"})
    session = register(bio_client)
    enroll(bio_client, session)  # enrolled but NOT opted in
    bio_client.cookies.clear()
    bad = [
        alone(bio_client, "ghost"),  # unknown user
        alone(bio_client, "nobio"),  # no biometrics
        alone(bio_client, "alice"),  # not opted in, even with the right samples
    ]
    assert {(r.status_code, r.text) for r in bad} == {(401, '{"detail":"Biometric login failed"}')}


def test_biometric_only_rejects_wrong_or_partial_samples(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    opt_in(bio_client, session)
    bio_client.cookies.clear()
    for audio, video in (
        (("a.webm", b"other-voice"), FACE),
        (VOICE, ("v.webm", b"other-face")),
        (VOICE, None),
        (None, FACE),
    ):
        assert alone(bio_client, audio=audio, video=video).status_code == 401
        state = bio_client.app.state  # stay under the lockout so each case is judged on its samples
        for throttle, key in ((state.alone_throttle, "testclient|alice"), (state.alone_account_throttle, "alice")):
            throttle.reset(key)


def test_biometric_only_is_locked_after_three_tries(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    opt_in(bio_client, session)
    bio_client.cookies.clear()
    wrong = ("a.webm", b"other-voice")
    codes = [alone(bio_client, audio=wrong).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    assert alone(bio_client).status_code == 429


def test_biometric_only_account_wide_lock_across_addresses(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    opt_in(bio_client, session)
    bio_client.cookies.clear()
    codes = []
    for index in range(14):
        attacker = TestClient(bio_client.app, client=(f"198.51.100.{index}", 5000))
        codes.append(alone(attacker, audio=("a.webm", b"other-voice")).status_code)
    assert codes[0] == 401 and codes[-1] == 429
    assert alone(TestClient(bio_client.app, client=("203.0.113.77", 1))).status_code == 429


# --- concurrency cap --------------------------------------------------------------------------


def test_only_two_biometric_jobs_run_at_once(enrolled):
    fake = enrolled.app.state.biometrics
    fake.release.clear()
    slots = enrolled.app.state.biometric_slots
    assert slots.acquire(blocking=False) and slots.acquire(blocking=False)
    import app.routes_biometrics as rb

    rb.SLOT_WAIT_SECONDS = 0.05
    try:
        response = enrolled.post("/auth/login/biometric", data={"mfa_token": mfa_token(enrolled)}, files=files(VOICE, FACE))
    finally:
        rb.SLOT_WAIT_SECONDS = 5
        slots.release()
        slots.release()
        fake.release.set()
    assert response.status_code == 401  # busy server is a plain failure for logins, not a bypass


def test_enroll_reports_busy_when_slots_are_taken(bio_client):
    session = register(bio_client)
    slots = bio_client.app.state.biometric_slots
    slots.acquire(), slots.acquire()
    import app.routes_biometrics as rb

    rb.SLOT_WAIT_SECONDS = 0.05
    try:
        assert enroll(bio_client, session).status_code == 503
    finally:
        rb.SLOT_WAIT_SECONDS = 5
        slots.release(), slots.release()


# --- crypto & real engine maths --------------------------------------------------------------


def test_cipher_round_trip_and_wrong_key():
    key = Fernet.generate_key().decode()
    cipher = TemplateCipher(key)
    blob = cipher.encrypt(b"secret-template")
    assert blob != b"secret-template" and cipher.decrypt(blob) == b"secret-template"
    assert TemplateCipher(Fernet.generate_key().decode()).decrypt(blob) is None
    assert cipher.decrypt(b"garbage") is None


def test_real_engine_thresholds():
    np = pytest.importorskip("numpy")
    engine = RealBiometrics(Settings(jwt_secret="x" * 40))
    base = np.ones(8, dtype=np.float32)
    raw = lambda v: np.asarray(v, dtype=np.float32).tobytes()  # noqa: E731
    assert engine.audio_matches(raw(base), raw(base * 2))
    assert not engine.audio_matches(raw(base), raw(-base))
    assert not engine.audio_matches(raw(base), raw(np.zeros(8)))
    assert engine.face_matches(raw(base), raw(base + 0.01))
    assert not engine.face_matches(raw(base), raw(base + 1.0))
    assert not engine.face_matches(raw(base), raw(np.ones(4)))  # shape mismatch is a non-match
    off = base.copy()
    off[0] = 0.4
    assert engine.audio_matches(raw(base), raw(off))
    assert not engine.audio_matches(raw(base), raw(base * 0 + np.arange(8)), strict=True)


def test_real_engine_missing_libraries_are_reported(monkeypatch):
    import sys

    from app.biometrics import BiometricError, BiometricUnavailable, audio, video

    monkeypatch.setitem(sys.modules, "resemblyzer", None)
    audio._build_encoder.cache_clear()
    with pytest.raises(BiometricUnavailable):
        audio.embed_audio(b"x", 5)
    audio._build_encoder.cache_clear()
    monkeypatch.setitem(sys.modules, "cv2", None)
    with pytest.raises(BiometricUnavailable):
        video.embed_face(b"x", 5)
    monkeypatch.setattr(audio.shutil, "which", lambda _: None)
    with pytest.raises(BiometricUnavailable):
        audio.to_wav_bytes(b"x", 5)
    pytest.importorskip("numpy")
    with pytest.raises(BiometricError):
        audio.wav_to_floats(b"not a wav")


def test_wav_parsing_rejects_short_clips():
    import io
    import wave

    pytest.importorskip("numpy")
    from app.biometrics import BiometricError, audio

    def wav(seconds):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(audio.SAMPLE_RATE)
            w.writeframes(b"\x00\x00" * int(audio.SAMPLE_RATE * seconds))
        return buf.getvalue()

    assert audio.wav_to_floats(wav(1.0)).size == audio.SAMPLE_RATE
    with pytest.raises(BiometricError):
        audio.wav_to_floats(wav(0.1))


def test_slots_are_shared_state_not_per_request(bio_client):
    assert isinstance(bio_client.app.state.biometric_slots, type(threading.BoundedSemaphore(1)))
