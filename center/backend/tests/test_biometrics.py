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
    """Link the face (webcam method) and/or the voice: two independent methods with their own templates."""
    data = PW if data is None else data
    response = None
    if audio is None and video is None:
        return client.post("/auth/me/webcam", data=data, headers=csrf(session))  # nothing to enroll: 422
    if audio is not None:
        response = client.post("/auth/me/voice", data=data, files=files(audio), headers=csrf(session))
    if video is not None:
        response = client.post("/auth/me/webcam", data=data, files=files(None, video), headers=csrf(session))
    return response


@pytest.fixture
def enrolled(bio_client):
    """Alice with voice (from the audio file) and face enrolled, then signed out."""
    session = register(bio_client)
    assert enroll(bio_client, session).status_code == 200
    bio_client.cookies.clear()
    return bio_client


def set_2fa(client, session, enabled=True, data=None):
    return client.put(
        "/auth/me/biometric-2fa", data={"enabled": str(enabled).lower(), **(data or PW)}, headers=csrf(session)
    )


@pytest.fixture
def enrolled_2fa(bio_client):
    """Alice with voice + face enrolled and the second factor switched ON, then signed out."""
    session = register(bio_client)
    assert enroll(bio_client, session).status_code == 200
    assert set_2fa(bio_client, session).status_code == 200
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
        client.post("/auth/login/voice", data={"username": "alice"}),
        client.post("/auth/login/webcam", data={"username": "alice"}),
        client.post("/auth/register/voice", data={"username": "alice"}),
        client.post("/auth/register/webcam", data={"username": "alice"}),
        client.post("/auth/me/voice", data=PW, headers=csrf(session)),
        client.post("/auth/me/webcam", data=PW, headers=csrf(session)),
        client.put("/auth/me/biometric-2fa", data={"enabled": "true", **PW}, headers=csrf(session)),
        client.request("DELETE", "/auth/me/voice", data=PW, headers=csrf(session)),
        client.request("DELETE", "/auth/me/webcam", data=PW, headers=csrf(session)),
    ]
    assert [r.status_code for r in attempts] == [503] * 10
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
    assert response.json() == {
        "has_password": True, "google_linked": False, "voice_login": True, "webcam_login": True,
        "has_audio": True, "has_face": True, "require_biometric_2fa": False, "passkey_count": 0,
    }  # fmt: skip
    me = bio_client.get("/auth/me").json()
    assert (me["has_audio"], me["has_face"]) == (True, True)
    with bio_client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert b"alice-voice" not in user.audio_embedding and b"alice-face" not in user.face_embedding
        assert bio_client.app.state.cipher.decrypt(user.audio_embedding) == b"A:alice-voice-samp"


def test_enroll_rules(bio_client):
    session = register(bio_client)
    assert bio_client.post("/auth/me/voice", data=PW, files=files(VOICE)).status_code == 403  # csrf
    assert enroll(bio_client, session, data={"password": "wrong-password"}).status_code == 403
    assert enroll(bio_client, session, audio=None, video=None).status_code == 422
    assert enroll(bio_client, session, audio=None).status_code == 200
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


def test_second_factor_opt_in_needs_an_enrolled_sample_and_the_password(bio_client):
    session = register(bio_client)
    assert set_2fa(bio_client, session).status_code == 422  # nothing enrolled
    enroll(bio_client, session, audio=VOICE, video=None)  # one factor is enough
    assert bio_client.put("/auth/me/biometric-2fa", data={"enabled": "true"}, headers=csrf(session)).status_code == 403
    assert bio_client.put("/auth/me/biometric-2fa", data={"enabled": "true", **PW}).status_code == 403  # csrf
    ok = set_2fa(bio_client, session)
    assert ok.status_code == 200 and ok.json()["require_biometric_2fa"] is True
    assert bio_client.get("/auth/me").json()["require_biometric_2fa"] is True


def test_second_factor_can_always_be_switched_off(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    set_2fa(bio_client, session)
    off = set_2fa(bio_client, session, enabled=False)
    assert off.status_code == 200 and off.json()["require_biometric_2fa"] is False
    assert set_2fa(bio_client, session, enabled=False).status_code == 200  # idempotent


def test_google_only_account_toggles_second_factor_without_a_password(bio_client):
    from tests.fakes import fake_google_verifier

    bio_client.app.state.google_verifier = fake_google_verifier
    session = bio_client.post("/auth/google", json={"id_token": "g1|gina@example.com"}).json()
    assert enroll(bio_client, session, data={}).status_code == 200
    assert set_2fa(bio_client, session, data={}).json()["require_biometric_2fa"] is True


# --- default OFF: password / Google login ignore enrolled biometrics ------------------------


def test_password_login_of_an_enrolled_account_signs_straight_in(enrolled):
    response = enrolled.post("/auth/login", json=CREDS)
    assert response.status_code == 200
    body = response.json()
    assert "mfa_required" not in body and "mfa_token" not in body
    assert set(body) == {"id", "username", "role", "csrf_token"}
    assert set(c.split("=")[0] for c in response.headers.get_list("set-cookie")) == {"sn_token", "sn_refresh"}
    assert enrolled.get("/auth/me").status_code == 200


def test_google_login_of_an_enrolled_account_signs_straight_in(bio_client):
    from tests.fakes import fake_google_verifier

    bio_client.app.state.google_verifier = fake_google_verifier
    session = bio_client.post("/auth/google", json={"id_token": "g1|gina@example.com"}).json()
    assert enroll(bio_client, session, data={}).status_code == 200  # Google-only: no password to confirm
    bio_client.cookies.clear()
    response = bio_client.post("/auth/google", json={"id_token": "g1|gina@example.com"})
    assert response.status_code == 200 and "mfa_required" not in response.json()
    assert set(c.split("=")[0] for c in response.headers.get_list("set-cookie")) == {"sn_token", "sn_refresh"}
    assert bio_client.get("/auth/me").status_code == 200


def test_enrolled_account_can_log_in_with_password_when_biometrics_are_switched_off(client):
    register(client)  # `client` runs with BIOMETRICS_ENABLED unset
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        user.audio_embedding, user.face_embedding, user.webcam_login = b"x", b"y", True
        db.commit()
    client.cookies.clear()
    assert client.get("/auth/config").json()["biometrics_enabled"] is False
    response = client.post("/auth/login", json=CREDS)
    assert response.status_code == 200 and "mfa_required" not in response.json()
    assert client.get("/auth/me").json()["has_audio"] is True


# --- second factor (opt-in) ---------------------------------------------------------------------


def test_password_login_returns_an_mfa_challenge_without_cookies(enrolled_2fa):
    response = enrolled_2fa.post("/auth/login", json=CREDS)
    body = response.json()
    assert set(body) == {"mfa_required", "mfa_token"} and body["mfa_required"] is True
    assert "set-cookie" not in response.headers
    assert enrolled_2fa.get("/auth/me").status_code == 401


def test_mfa_token_is_a_five_minute_typed_token_bound_to_user_and_version(enrolled_2fa):
    import jwt

    from sn_shared.security import ALGORITHM, ISSUER, get_jwt_secret

    claims = jwt.decode(mfa_token(enrolled_2fa), get_jwt_secret(), algorithms=[ALGORITHM], issuer=ISSUER)
    assert claims["typ"] == "mfa" and claims["ver"] == 0 and claims["exp"] - claims["iat"] == 300


def test_google_login_with_second_factor_on_returns_a_challenge_without_cookies(bio_client):
    from tests.fakes import fake_google_verifier

    bio_client.app.state.google_verifier = fake_google_verifier
    session = bio_client.post("/auth/google", json={"id_token": "g1|gina@example.com"}).json()
    enroll(bio_client, session, data={})
    set_2fa(bio_client, session, data={})
    bio_client.cookies.clear()
    response = bio_client.post("/auth/google", json={"id_token": "g1|gina@example.com"})
    assert response.json()["mfa_required"] is True and "set-cookie" not in response.headers
    assert bio_client.get("/auth/me").status_code == 401


def test_switching_the_second_factor_off_again_restores_direct_login(bio_client):
    session = register(bio_client)
    enroll(bio_client, session)
    set_2fa(bio_client, session)
    set_2fa(bio_client, session, enabled=False)
    bio_client.cookies.clear()
    assert "mfa_required" not in bio_client.post("/auth/login", json=CREDS).json()


def test_mfa_with_matching_samples_issues_a_session(enrolled_2fa):
    response = enrolled_2fa.post(
        "/auth/login/biometric", data={"mfa_token": mfa_token(enrolled_2fa)}, files=files(VOICE, FACE)
    )
    assert response.status_code == 200
    assert response.json()["username"] == "alice" and response.json()["csrf_token"]
    assert enrolled_2fa.get("/auth/me").status_code == 200
    assert set(c.split("=")[0] for c in response.headers.get_list("set-cookie")) == {"sn_token", "sn_refresh"}
    assert set(enrolled_2fa.app.state.biometrics.strict_calls) == {False}  # normal thresholds


def test_mfa_needs_every_enrolled_factor_even_when_the_voice_matches_via_video(enrolled_2fa):
    video = ("v.webm", b"alice-voice-sample")  # fake engine derives both embeddings from the same bytes
    response = enrolled_2fa.post(
        "/auth/login/biometric", data={"mfa_token": mfa_token(enrolled_2fa)}, files=files(None, video)
    )
    assert response.status_code == 401  # face differs: every factor must match


@pytest.mark.parametrize(
    "probe",
    [
        files(("a.webm", b"someone-else-voice"), FACE),  # wrong voice
        files(VOICE, ("v.webm", b"someone-else-face")),  # wrong face
        files(VOICE, None),  # missing face
        files(None, FACE),  # missing voice
        {},  # nothing at all
        files(("a.webm", b"bad"), FACE),  # unusable sample
    ],
)
def test_mfa_rejects_wrong_or_missing_samples(enrolled_2fa, probe):
    response = enrolled_2fa.post(
        "/auth/login/biometric", data={"mfa_token": mfa_token(enrolled_2fa)}, files=probe or None
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Biometric verification failed"
    assert enrolled_2fa.get("/auth/me").status_code == 401


def test_mfa_with_one_enrolled_factor_needs_only_that_factor(bio_client):
    session = register(bio_client)
    enroll(bio_client, session, audio=VOICE, video=None)
    set_2fa(bio_client, session)
    bio_client.cookies.clear()
    ok = bio_client.post("/auth/login/biometric", data={"mfa_token": mfa_token(bio_client)}, files=files(VOICE))
    assert ok.status_code == 200


def test_mfa_token_must_be_valid_unexpired_and_typed(enrolled_2fa):
    import time

    from tests.helpers import forge

    good = mfa_token(enrolled_2fa)
    uid = enrolled_2fa.app.state.session_factory().scalar(select(User.id))
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
        r = enrolled_2fa.post("/auth/login/biometric", data={"mfa_token": token}, files=files(VOICE, FACE))
        assert r.status_code == 401, token
        assert r.json()["detail"] == "Invalid or expired login session"


def test_mfa_failures_are_throttled_per_user_and_ip(enrolled_2fa):
    token = mfa_token(enrolled_2fa)
    wrong = files(("a.webm", b"nope"), FACE)
    codes = [
        enrolled_2fa.post("/auth/login/biometric", data={"mfa_token": token}, files=wrong).status_code
        for _ in range(7)
    ]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    # Even the right sample is refused while locked.
    right = enrolled_2fa.post("/auth/login/biometric", data={"mfa_token": token}, files=files(VOICE, FACE))
    assert right.status_code == 429


def test_mfa_account_wide_lock_across_addresses(enrolled_2fa):
    token = mfa_token(enrolled_2fa)
    codes = []
    for index in range(24):
        attacker = TestClient(enrolled_2fa.app, client=(f"198.51.100.{index}", 5000))
        wrong = files(("a.webm", b"nope"), FACE)
        codes.append(attacker.post("/auth/login/biometric", data={"mfa_token": token}, files=wrong).status_code)
    assert codes[0] == 401 and codes[-1] == 429


def test_mfa_success_resets_the_counter(enrolled_2fa):
    token = mfa_token(enrolled_2fa)
    wrong = files(("a.webm", b"nope"), FACE)
    for _ in range(4):
        enrolled_2fa.post("/auth/login/biometric", data={"mfa_token": token}, files=wrong)
    ok = enrolled_2fa.post("/auth/login/biometric", data={"mfa_token": token}, files=files(VOICE, FACE))
    assert ok.status_code == 200
    for _ in range(4):
        assert enrolled_2fa.post("/auth/login/biometric", data={"mfa_token": token}, files=wrong).status_code == 401


def test_password_login_fails_closed_when_biometrics_are_switched_off_server_wide(client):
    """Never silently skip a second factor the user asked for: 503, and no cookies."""
    register(client)  # `client` runs with BIOMETRICS_ENABLED unset
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        user.audio_embedding, user.biometric_2fa = b"x", True
        db.commit()
    client.cookies.clear()
    response = client.post("/auth/login", json=CREDS)
    assert response.status_code == 503 and response.json() == {"detail": "Biometrics are not available"}
    assert "set-cookie" not in response.headers and client.get("/auth/me").status_code == 401


def test_google_login_fails_closed_too(google_client):
    from sqlalchemy import update

    google_client.post("/auth/google", json={"id_token": "g1|gina@example.com"})
    with google_client.app.state.session_factory() as db:
        db.execute(update(User).values(audio_embedding=b"x", biometric_2fa=True))
        db.commit()
    google_client.cookies.clear()
    assert google_client.post("/auth/google", json={"id_token": "g1|gina@example.com"}).status_code == 503


def test_second_factor_flag_without_samples_does_not_block_login(client):
    register(client)
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        user.biometric_2fa = True  # inconsistent row: nothing enrolled, nothing to verify
        db.commit()
    client.cookies.clear()
    assert client.post("/auth/login", json=CREDS).status_code == 200


def test_body_limit_covers_the_second_factor_path():
    from app.bodylimit import BIOMETRIC_MAX_BYTES, DEFAULT_MAX_BYTES, limit_for

    assert limit_for("/auth/login/biometric", True) == BIOMETRIC_MAX_BYTES
    assert limit_for("/auth/login/biometric", False) == DEFAULT_MAX_BYTES


# --- concurrency cap --------------------------------------------------------------------------


def test_only_two_biometric_jobs_run_at_once(enrolled):
    fake = enrolled.app.state.biometrics
    fake.release.clear()
    slots = enrolled.app.state.biometric_slots
    assert slots.acquire(blocking=False) and slots.acquire(blocking=False)
    import app.routes_biometrics as rb

    rb.SLOT_WAIT_SECONDS = 0.05
    try:
        response = enrolled.post("/auth/login/webcam", data={"username": "alice"}, files=files(VOICE, FACE))
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
