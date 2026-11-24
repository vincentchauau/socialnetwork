"""Best-effort webcam liveness: a random challenge-response plus cheap anti-spoof sanity checks.

NOT a certified presentation-attack-detection (PAD) system. It raises the bar against a still photo and a
generic pre-recorded video; a live deepfake or a real-time targeted video held up to the camera can still
pass. Everything here is pure (no numpy, no dlib): landmarks are plain (x, y) sequences so it is testable
anywhere. Directions are as seen by the USER on an UNMIRRORED stream (the frontend must not mirror the
recorded video, only its preview): "turn_left" = the user turns their head to their own left, which moves
the nose toward the image's right edge (x grows).
"""

import logging
import math
import random
from typing import Sequence

from fastapi import HTTPException, Request

from api.center.passkeys import ChallengeStore, PasskeyError, mint_challenge, read_challenge

audit = logging.getLogger("auth.audit")

PURPOSE = "liveness"
CHALLENGE_TTL_SECONDS = 60
ACTIONS = ("blink", "turn_left", "turn_right", "open_mouth")
ACTIONS_PER_CHALLENGE = 2
MAX_VIDEO_BYTES = 15_000_000
MAX_EXTRA_ACTION_EVENTS = 1  # detected events beyond the requested ones (a stray blink); all-four clips fail
ANALYSES_MAX_PER_IP = 20  # video analyses per address per window (they are the expensive part)
ANALYSES_WINDOW_SECONDS = 300.0

# Detection thresholds (landmark ratios, resolution independent).
EAR_CLOSED = 0.2  # eye aspect ratio below this = eye closed
EAR_OPEN = 0.25  # ... and back above this = blink completed
MAR_OPEN = 0.35  # mouth aspect ratio (inner opening / mouth width) above this = mouth open
MAR_CLOSED = 0.2  # ... and back below this = mouth closed again
YAW_TURN = 0.12  # nose offset (fraction of face width) from the neutral start = head turned
YAW_REARM = 0.06  # back inside this band, a further turn counts again
NEUTRAL_FRAMES = 3  # first frames that define the neutral yaw

# Anti-spoof sanity checks.
MIN_FACE_FRAME_RATIO = 0.8  # exactly one face in at least this share of the sampled frames
MIN_FRAMES = 6  # fewer analysable frames than this is not a usable clip
MIN_JITTER = 0.004  # box centre/size must move at least this (fraction of face width): a still image fails
SAME_PERSON_MAX_DISTANCE = 0.5  # first vs last frame face-embedding distance

Point = tuple[float, float]


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(eye: Sequence[Point]) -> float:
    """EAR of the 6 landmarks of one eye (face_recognition order); 0.0 when degenerate."""
    if len(eye) != 6:
        return 0.0
    width = _dist(eye[0], eye[3])
    return (_dist(eye[1], eye[5]) + _dist(eye[2], eye[4])) / (2 * width) if width else 0.0


def mouth_aspect_ratio(top_lip: Sequence[Point], bottom_lip: Sequence[Point]) -> float:
    """Inner mouth opening over mouth width (face_recognition 12-point lips); 0.0 when degenerate."""
    if len(top_lip) != 12 or len(bottom_lip) != 12:
        return 0.0
    width = _dist(top_lip[0], top_lip[6])
    return _dist(top_lip[9], bottom_lip[9]) / width if width else 0.0


def yaw_proxy(nose_bridge: Sequence[Point], chin: Sequence[Point]) -> float:
    """Nose-bridge tip x relative to the middle of the jaw, as a fraction of the face width (unmirrored image)."""
    if not nose_bridge or len(chin) != 17:
        return 0.0
    left, right = chin[0][0], chin[16][0]
    width = right - left
    return (nose_bridge[-1][0] - (left + right) / 2) / width if width else 0.0


def detect_actions(frames: Sequence[tuple[float, float, float]]) -> list[str]:
    """Ordered actions seen in per-frame (ear, mar, yaw) features. Never raises."""
    detected: list[str] = []
    try:
        neutral_values = sorted(f[2] for f in frames[:NEUTRAL_FRAMES])
        neutral = neutral_values[len(neutral_values) // 2] if neutral_values else 0.0
        eye_closed = mouth_open = False
        turned = 0  # +1 turned left, -1 turned right, 0 neutral
        for ear, mar, yaw in frames:
            if ear < EAR_CLOSED:
                eye_closed = True
            elif ear > EAR_OPEN and eye_closed:
                eye_closed = False
                detected.append("blink")
            if mar > MAR_OPEN:
                mouth_open = True
            elif mar < MAR_CLOSED and mouth_open:
                mouth_open = False
                detected.append("open_mouth")
            delta = yaw - neutral
            if turned == 0 and abs(delta) > YAW_TURN:
                turned = 1 if delta > 0 else -1
                detected.append("turn_left" if turned > 0 else "turn_right")
            elif turned != 0 and abs(delta) < YAW_REARM:
                turned = 0
    except (TypeError, ValueError, IndexError):
        return []
    return detected


def in_order(requested: Sequence[str], detected: Sequence[str]) -> bool:
    """True when `requested` appears in `detected` as an ordered subsequence (extra movements are tolerated)."""
    remaining = iter(detected)
    return bool(requested) and all(action in remaining for action in requested)


def matches_challenge(requested: Sequence[str], detected: Sequence[str]) -> bool:
    """In order AND not much else: a single clip performing every action must not pass any challenge."""
    return in_order(requested, detected) and len(detected) - len(requested) <= MAX_EXTRA_ACTION_EVENTS


def warn_if_optional(settings) -> None:
    """Startup warning: in production with webcam on but liveness optional, a client can simply skip it."""
    if settings.production and settings.biometrics_enabled and not settings.liveness_required:
        audit.warning("liveness is optional (LIVENESS_REQUIRED unset): a client can skip the challenge; set LIVENESS_REQUIRED=1")


def face_present_enough(face_counts: Sequence[int]) -> bool:
    """Exactly one face in most sampled frames, and enough frames to judge."""
    if len(face_counts) < MIN_FRAMES:
        return False
    return sum(1 for n in face_counts if n == 1) / len(face_counts) >= MIN_FACE_FRAME_RATIO


def has_motion(boxes: Sequence[tuple[float, float, float, float]]) -> bool:
    """(top, right, bottom, left) boxes: the face must move or change size at least slightly (still image = fail)."""
    try:
        norm = [((l + r) / 2, (t + b) / 2, r - l) for t, r, b, l in boxes]
        width = max(w for _, _, w in norm)
        if width <= 0:
            return False
        return any((max(v) - min(v)) / width >= MIN_JITTER for v in zip(*norm))
    except (TypeError, ValueError):
        return False


def same_person(first: Sequence[float], last: Sequence[float], limit: float = SAME_PERSON_MAX_DISTANCE) -> bool:
    """First and last frame embeddings (equal length) are close enough to be one person."""
    if not first or len(first) != len(last):
        return False
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, last))) <= limit


# --- challenge tokens -----------------------------------------------------------------------------


def new_actions() -> list[str]:
    return random.SystemRandom().sample(ACTIONS, ACTIONS_PER_CHALLENGE)


def issue_token(actions: Sequence[str]) -> str:
    """Signed, 60 s, single-use (consumed on read); bound to the ordered action list."""
    return mint_challenge(PURPOSE, ",".join(actions).encode(), ttl_seconds=CHALLENGE_TTL_SECONDS)


def read_token(token: str, store: ChallengeStore) -> list[str]:
    """Verify and CONSUME a challenge token; PasskeyError for anything wrong (expired, replayed, tampered)."""
    actions = read_challenge(token, PURPOSE, store).challenge.decode().split(",")
    if len(actions) != ACTIONS_PER_CHALLENGE or len(set(actions)) != len(actions) or not set(actions) <= set(ACTIONS):
        raise PasskeyError("bad actions")
    return actions


def liveness_ok(request: Request, token: str | None, video) -> bool:
    """Optional mode: no token = pass. Required mode (LIVENESS_REQUIRED=1): no token = fail.

    With a token: it is consumed and the clip must show the requested actions in order. A failure is a plain
    False (the endpoint answers with its usual generic failure); the reason goes to the log only.
    """
    from api.center.deps import client_ip, settings_of, too_many
    from api.center.routes_biometrics import biometric_slot, read_upload

    if not token:
        if settings_of(request).liveness_required:
            audit.warning("liveness failed: token missing but required")
            return False
        return True
    try:
        actions = read_token(token, request.app.state.passkey_challenges)
    except PasskeyError:
        audit.warning("liveness failed: invalid, expired or reused challenge token")
        return False
    if not request.app.state.liveness_analysis_throttle.check_and_record(client_ip(request)):
        audit.warning("liveness analysis throttled ip=%s", client_ip(request))
        raise too_many()
    try:
        raw = read_upload(video, MAX_VIDEO_BYTES)
        if video is not None:
            video.file.seek(0)  # the endpoint reads the same clip again for the face
        if not raw:
            audit.warning("liveness failed: no video")
            return False
        with biometric_slot(request) as engine:
            finder = getattr(engine, "liveness_actions", None)
            detected = list(finder(raw)) if finder else []
    except HTTPException as exc:
        audit.warning("liveness failed: sample error status=%s", exc.status_code)
        return False
    if not matches_challenge(actions, detected):
        audit.warning("liveness failed: requested=%s detected=%s", actions, detected)
        return False
    return True
