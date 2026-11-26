import time

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from api.center import liveness as lv
from api.center.main import create_app
from api.center.passkeys import mint_challenge
from sn_shared.security import INTERNAL_ALGORITHM, get_jwt_secret
from tests.center.fakes import FakeBiometrics
from tests.center.helpers import CREDS, csrf, register


def clip(name="alice", actions=("blink", "turn_left"), flag=""):
    return f"FACE:{name}|ACTIONS:{','.join(actions)}{flag}".encode()


def challenge(client):
    body = client.get("/auth/liveness/challenge").json()
    return body["challenge_token"], body["actions"]


def login(client, token, video, username="alice"):
    data = {"username": username}
    if token is not None:
        data["liveness_token"] = token
    return client.post("/auth/login/webcam", data=data, files={"video": ("v.webm", video)})


@pytest.fixture
def required_client(monkeypatch):
    monkeypatch.setenv("BIOMETRICS_ENABLED", "1")
    monkeypatch.setenv("LIVENESS_REQUIRED", "1")
    monkeypatch.setenv("DATA_KEY", Fernet.generate_key().decode())
    app = create_app("sqlite://")
    app.state.biometrics = FakeBiometrics()
    with TestClient(app) as test_client:
        yield test_client


def enrolled(client):
    """alice with a webcam login, enrolled through the optional (token-less) path."""
    r = client.post("/auth/register/webcam", data={"username": "alice"}, files={"video": ("v.webm", clip())})
    assert r.status_code == 201, r.text
    client.cookies.clear()


# --- pure functions ---

EYE_OPEN = [(0, 0), (1, -1), (2, -1), (3, 0), (2, 1), (1, 1)]
EYE_SHUT = [(0, 0), (1, -0.1), (2, -0.1), (3, 0), (2, 0.1), (1, 0.1)]


def lips(gap):
    top = [(i, 0) for i in range(7)] + [(5, 0), (4, 0), (3, 0), (2, 0), (1, 0)]
    bottom = [(i, 0) for i in range(7)] + [(1, gap), (2, gap), (3, gap), (4, gap), (5, gap)]
    return top, bottom


def test_ear_mar_yaw_math():
    assert lv.eye_aspect_ratio(EYE_OPEN) > lv.EAR_OPEN
    assert lv.eye_aspect_ratio(EYE_SHUT) < lv.EAR_CLOSED
    assert lv.eye_aspect_ratio([]) == 0.0
    assert lv.eye_aspect_ratio([(0, 0)] * 6) == 0.0
    assert lv.mouth_aspect_ratio(*lips(3)) > lv.MAR_OPEN
    assert lv.mouth_aspect_ratio(*lips(0.2)) < lv.MAR_CLOSED
    assert lv.mouth_aspect_ratio([], []) == 0.0
    assert lv.mouth_aspect_ratio(*([[(0, 0)] * 12] * 2)) == 0.0
    chin = [(0, 0)] * 16 + [(100, 0)]
    assert lv.yaw_proxy([(50, 0)], chin) == 0
    assert lv.yaw_proxy([(70, 0)], chin) == pytest.approx(0.2)
    assert lv.yaw_proxy([], chin) == 0.0 and lv.yaw_proxy([(1, 1)], [(0, 0)] * 17) == 0.0


def test_detect_actions_in_order_and_direction():
    neutral = [(0.3, 0.1, 0.0)] * 4
    blink = [(0.1, 0.1, 0.0), (0.3, 0.1, 0.0)]
    mouth = [(0.3, 0.6, 0.0), (0.3, 0.1, 0.0)]
    left = [(0.3, 0.1, 0.2), (0.3, 0.1, 0.0)]
    right = [(0.3, 0.1, -0.2), (0.3, 0.1, 0.0)]
    seen = lv.detect_actions(neutral + blink + left + mouth + right)
    assert seen == ["blink", "turn_left", "open_mouth", "turn_right"]
    assert lv.detect_actions(neutral) == []
    assert lv.detect_actions([]) == []
    assert lv.detect_actions([("x",)]) == []
    assert lv.detect_actions(neutral + [(0.1, 0.1, 0.0)]) == []  # eye never recovers


def test_in_order_and_sanity_checks():
    assert lv.in_order(["blink", "turn_left"], ["open_mouth", "blink", "blink", "turn_left"])
    assert not lv.in_order(["blink", "turn_left"], ["turn_left", "blink"])
    assert not lv.in_order(["blink"], []) and not lv.in_order([], ["blink"])
    assert lv.face_present_enough([1] * 10)
    assert not lv.face_present_enough([1] * 5)  # too few frames
    assert not lv.face_present_enough([1, 0, 0, 1, 2, 1, 1, 1])
    still = [(10, 60, 60, 10)] * 10
    moving = [(10 + i, 60 + i, 60 + i, 10) for i in range(10)]
    assert not lv.has_motion(still) and lv.has_motion(moving)
    assert not lv.has_motion([]) and not lv.has_motion([(1, 1, 1, 1)] * 3)
    assert lv.same_person([0.0, 0.0], [0.1, 0.1]) and not lv.same_person([0.0], [1.0])
    assert not lv.same_person([], []) and not lv.same_person([0.0], [0.0, 1.0])


def test_real_engine_never_raises_on_garbage():
    from api.center.biometrics.liveness_video import liveness_actions

    assert liveness_actions(b"") == []
    assert liveness_actions(b"not a video") == []


# --- challenge endpoint ---


def test_challenge_shape_and_randomness(bio_client):
    body = bio_client.get("/auth/liveness/challenge").json()
    assert set(body) == {"challenge_token", "actions", "expires_in"} and body["expires_in"] == 60
    assert len(body["actions"]) == 2 and len(set(body["actions"])) == 2 and set(body["actions"]) <= set(lv.ACTIONS)
    seen = {tuple(bio_client.post("/auth/liveness/challenge").json()["actions"]) for _ in range(15)}
    assert len(seen) > 1


def test_challenge_off_without_biometrics(client):
    assert client.get("/auth/liveness/challenge").status_code == 503


def test_challenge_origin_and_throttle(bio_client):
    assert bio_client.post("/auth/liveness/challenge", headers={"Origin": "https://evil.example"}).status_code == 403
    codes = [bio_client.get("/auth/liveness/challenge").status_code for _ in range(22)]
    assert codes[0] == 200 and codes[-1] == 429


def test_config_flags(bio_client):
    assert bio_client.get("/auth/config").json()["liveness_enabled"] is True
    assert bio_client.get("/auth/config").json()["liveness_required"] is False


def test_config_flags_required(required_client):
    assert required_client.get("/auth/config").json()["liveness_required"] is True


def test_config_flags_off(client):
    assert client.get("/auth/config").json()["liveness_enabled"] is False


# --- verification ---


def test_login_with_correct_actions_in_order(bio_client):
    enrolled(bio_client)
    token, actions = challenge(bio_client)
    assert login(bio_client, token, clip(actions=actions)).status_code == 200


def test_optional_mode_allows_missing_token(bio_client):
    enrolled(bio_client)
    assert login(bio_client, None, clip()).status_code == 200


@pytest.mark.parametrize("make", [
    lambda a: clip(actions=list(reversed(a))),  # wrong order
    lambda a: clip(actions=a[:1]),  # missing action
    lambda a: clip(actions=[]),
    lambda a: clip(actions=a, flag="|STATIC"),  # still image
    lambda a: clip(actions=a, flag="|SWAP"),  # another person midway
])
def test_failures_are_identical_401(bio_client, make):
    enrolled(bio_client)
    token, actions = challenge(bio_client)
    wrong_face = login(bio_client, None, clip(name="mallory"))
    bad = login(bio_client, token, make(actions))
    assert bad.status_code == 401 and bad.json() == wrong_face.json()


def test_replay_is_refused(bio_client):
    enrolled(bio_client)
    token, actions = challenge(bio_client)
    assert login(bio_client, token, clip(actions=actions)).status_code == 200
    assert login(bio_client, token, clip(actions=actions)).status_code == 401


def _expired(token):
    claims = jwt.decode(token, get_jwt_secret(), algorithms=[INTERNAL_ALGORITHM], options={"verify_exp": False})
    return jwt.encode({**claims, "exp": int(time.time()) - 5}, get_jwt_secret(), algorithm=INTERNAL_ALGORITHM)


BAD_TOKENS = {
    "tampered": lambda t: t[:-3] + "AAA",
    "garbage": lambda t: "garbage",
    "expired": _expired,
    "other_purpose": lambda t: mint_challenge("login", b"blink,turn_left", ttl_seconds=60),
    "duplicate_actions": lambda t: mint_challenge("liveness", b"blink,blink", ttl_seconds=60),
    "unknown_action": lambda t: mint_challenge("liveness", b"blink,fly", ttl_seconds=60),
}


@pytest.mark.parametrize("kind", sorted(BAD_TOKENS))
def test_bad_tokens_are_refused(bio_client, kind):
    enrolled(bio_client)
    token, _ = challenge(bio_client)
    assert login(bio_client, BAD_TOKENS[kind](token), clip(actions=["blink", "turn_left"])).status_code == 401


def test_token_without_video_fails(bio_client):
    enrolled(bio_client)
    token, _ = challenge(bio_client)
    r = bio_client.post("/auth/login/webcam", data={"username": "alice", "liveness_token": token})
    assert r.status_code == 401


def test_identify_checks_liveness(bio_client):
    enrolled(bio_client)
    token, actions = challenge(bio_client)
    bad = bio_client.post("/auth/login/webcam", data={"liveness_token": token},
                          files={"video": ("v.webm", clip(actions=actions[:1]))})
    assert bad.status_code == 401
    token, actions = challenge(bio_client)
    ok = bio_client.post("/auth/login/webcam", data={"liveness_token": token},
                         files={"video": ("v.webm", clip(actions=actions))})
    assert ok.status_code == 200


# --- register / link ---


def test_register_with_token(bio_client):
    token, actions = challenge(bio_client)
    bad = bio_client.post("/auth/register/webcam", data={"username": "bob", "liveness_token": token},
                          files={"video": ("v.webm", clip("bob", actions[:1]))})
    assert bad.status_code == 422
    token, actions = challenge(bio_client)
    ok = bio_client.post("/auth/register/webcam", data={"username": "bob", "liveness_token": token},
                         files={"video": ("v.webm", clip("bob", actions))})
    assert ok.status_code == 201


def test_combined_register_with_token(bio_client):
    token, actions = challenge(bio_client)
    bad = bio_client.post("/auth/register/combined", data={"username": "bob", "liveness_token": token},
                          files={"webcam_video": ("v.webm", clip("bob", actions[:1]))})
    assert bad.status_code == 422
    token, actions = challenge(bio_client)
    ok = bio_client.post("/auth/register/combined", data={"username": "bob", "liveness_token": token},
                         files={"webcam_video": ("v.webm", clip("bob", actions))})
    assert ok.status_code == 201


def test_link_with_token(bio_client):
    session = register(bio_client)
    pw = CREDS["password"]
    token, actions = challenge(bio_client)
    bad = bio_client.post("/auth/me/webcam", data={"password": pw, "liveness_token": token},
                          files={"video": ("v.webm", clip(actions=actions[:1]))}, headers=csrf(session))
    assert bad.status_code == 422
    token, actions = challenge(bio_client)
    ok = bio_client.post("/auth/me/webcam", data={"password": pw, "liveness_token": token},
                         files={"video": ("v.webm", clip(actions=actions))}, headers=csrf(session))
    assert ok.status_code == 200 and ok.json()["webcam_login"] is True


# --- required mode ---


def test_required_mode_rejects_missing_token_everywhere(required_client):
    c = required_client
    r = c.post("/auth/register/webcam", data={"username": "alice"}, files={"video": ("v.webm", clip())})
    assert r.status_code == 422
    token, actions = challenge(c)
    r = c.post("/auth/register/webcam", data={"username": "alice", "liveness_token": token},
               files={"video": ("v.webm", clip(actions=actions))})
    assert r.status_code == 201
    c.cookies.clear()
    assert login(c, None, clip()).status_code == 401
    assert c.post("/auth/login/webcam", files={"video": ("v.webm", clip())}).status_code == 401
    token, actions = challenge(c)
    assert login(c, token, clip(actions=actions)).status_code == 200


def test_required_mode_link(required_client):
    c = required_client
    session = register(c)
    data = {"password": CREDS["password"]}
    r = c.post("/auth/me/webcam", data=data, files={"video": ("v.webm", clip())}, headers=csrf(session))
    assert r.status_code == 422
    token, actions = challenge(c)
    r = c.post("/auth/me/webcam", data={**data, "liveness_token": token},
               files={"video": ("v.webm", clip(actions=actions))}, headers=csrf(session))
    assert r.status_code == 200


# --- review fixes: analysis throttle, slot, extra events, startup warning ---


def _count_calls(client):
    engine, calls = client.app.state.biometrics, []
    original = engine.liveness_actions

    def counting(raw):
        calls.append(client.app.state.biometric_slots._value)  # free slots while analysing
        return original(raw)

    engine.liveness_actions = counting
    return calls


def test_analysis_runs_inside_a_biometric_slot(bio_client):
    enrolled(bio_client)
    calls = _count_calls(bio_client)
    token, actions = challenge(bio_client)
    assert login(bio_client, token, clip(actions=actions)).status_code == 200
    assert calls == [bio_client.app.state.biometric_slots._value - 1]


def test_analysis_is_throttled_per_ip(bio_client):
    from api.center.throttle import AttemptThrottle

    enrolled(bio_client)
    bio_client.app.state.liveness_analysis_throttle = AttemptThrottle(2, 300.0)
    calls = _count_calls(bio_client)
    codes = []
    for _ in range(3):
        token, actions = challenge(bio_client)
        codes.append(login(bio_client, token, clip(actions=actions[:1])).status_code)
    assert codes == [401, 401, 429] and len(calls) == 2


def test_locked_account_skips_the_analysis(bio_client):
    enrolled(bio_client)
    calls = _count_calls(bio_client)
    codes = []
    for _ in range(7):
        token, actions = challenge(bio_client)
        codes.append(login(bio_client, token, clip(actions=actions[:1])).status_code)
    assert codes[0] == 401 and codes[-1] == 429 and set(codes) == {401, 429}
    assert len(calls) == codes.count(401)  # failed liveness counts against the login throttle; locked = no analysis


def test_identify_lockout_skips_the_analysis(bio_client):
    enrolled(bio_client)
    calls = _count_calls(bio_client)
    codes = []
    for _ in range(8):
        token, actions = challenge(bio_client)
        r = bio_client.post("/auth/login/webcam", data={"liveness_token": token},
                            files={"video": ("v.webm", clip(actions=actions[:1]))})
        codes.append(r.status_code)
    assert codes[0] == 401 and codes[-1] == 429
    assert len(calls) == codes.count(401)


def test_clip_with_too_many_extra_actions_fails():
    assert lv.matches_challenge(["blink", "turn_left"], ["blink", "turn_left"])
    assert lv.matches_challenge(["blink", "turn_left"], ["open_mouth", "blink", "turn_left"])
    every = ["blink", "open_mouth", "turn_left", "turn_right"]
    assert lv.in_order(["blink", "turn_left"], every)
    assert not lv.matches_challenge(["blink", "turn_left"], every)


def test_all_four_actions_clip_is_refused_by_the_endpoint(bio_client):
    enrolled(bio_client)
    token = mint_challenge("liveness", b"blink,turn_left", ttl_seconds=60)
    every = clip(actions=["blink", "open_mouth", "turn_left", "turn_right"])
    assert login(bio_client, token, every).status_code == 401


def test_startup_warning_when_optional_in_production(caplog):
    from types import SimpleNamespace

    cases = [(True, True, False, True), (True, True, True, False), (True, False, False, False), (False, True, False, False)]
    for production, bio, required, warned in cases:
        caplog.clear()
        lv.warn_if_optional(SimpleNamespace(production=production, biometrics_enabled=bio, liveness_required=required))
        assert any("LIVENESS_REQUIRED" in r.getMessage() for r in caplog.records) is warned
