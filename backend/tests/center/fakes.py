"""Injectable fakes: biometrics engine and Google verifier."""

import threading

from api.center.biometrics import BiometricError, BiometricUnavailable
from api.center.google_auth import GoogleAuthError, GoogleIdentity
from api.center.mailer import Message


class FakeBiometrics:
    """Embedding = a tag plus the first bytes of the sample; matching = equality."""

    def __init__(self) -> None:
        self.strict_calls: list[bool] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def audio_embedding(self, raw: bytes) -> bytes:
        self.entered.set()
        self.release.wait(5)
        if raw.startswith(b"bad") or b"silent" in raw:
            raise BiometricError("unusable")
        if raw.startswith(b"missing-lib"):
            raise BiometricUnavailable("no ffmpeg")
        return b"A:" + raw[:16]

    def face_embedding(self, raw: bytes) -> bytes:
        if raw.startswith(b"bad"):
            raise BiometricError("no face")
        return b"F:" + raw[:16]

    def face_distance(self, stored: bytes, probe: bytes) -> float:
        """Faces tagged b'f<number>-...' have distance |a-b|; other faces: 0 if equal, else 9."""
        a, b = _face_value(stored), _face_value(probe)
        if a is not None and b is not None:
            return abs(a - b)
        return 0.0 if stored == probe else 9.0

    def audio_similarity(self, stored: bytes, probe: bytes) -> float:
        """Voices tagged b'v<number>-...' have similarity 1-|a-b|; other voices: 1 if equal, else 0."""
        a, b = _tagged_value(stored, b"A:v"), _tagged_value(probe, b"A:v")
        if a is not None and b is not None:
            return 1.0 - abs(a - b)
        return 1.0 if stored == probe else 0.0

    def audio_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool:
        self.strict_calls.append(strict)
        return self.audio_similarity(stored, probe) >= (0.88 if strict else 0.8)

    def face_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool:
        self.strict_calls.append(strict)
        return stored == probe

    def liveness_actions(self, raw: bytes) -> list[str]:
        """b'FACE:alice|ACTIONS:blink,turn_left' -> ['blink','turn_left']; a '|STATIC' (still image) or
        '|SWAP' (another person midway) marker fails the anti-spoof checks -> []."""
        text = raw.decode("utf-8", "ignore")
        if "|STATIC" in text or "|SWAP" in text or "|ACTIONS:" not in text:
            return []
        listed = text.split("|ACTIONS:", 1)[1].split("|", 1)[0]
        return [a for a in listed.split(",") if a]


def _tagged_value(embedding: bytes, prefix: bytes) -> float | None:
    if not embedding.startswith(prefix):
        return None
    try:
        return float(embedding[len(prefix):].split(b"-", 1)[0])
    except ValueError:
        return None


def _face_value(embedding: bytes) -> float | None:
    return _tagged_value(embedding, b"F:f")


def fake_google_verifier(token: str) -> GoogleIdentity:
    """Tokens look like 'sub|email'; anything starting with 'bad' is rejected."""
    if token.startswith("bad"):
        raise GoogleAuthError("Invalid Google token")
    sub, email = token.split("|", 1)
    return GoogleIdentity(sub=sub, email=email)


class FakeMailer:
    """Collects messages instead of speaking SMTP; `fail` makes every send raise."""

    def __init__(self) -> None:
        self.sent: list[Message] = []
        self.fail = False

    def send(self, message: Message) -> None:
        if self.fail:
            raise RuntimeError("smtp is down")
        self.sent.append(message)

    def to(self, address: str) -> list[Message]:
        return [m for m in self.sent if m.to == address]
