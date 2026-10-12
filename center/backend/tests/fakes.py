"""Injectable fakes: biometrics engine and Google verifier."""

import threading

from app.biometrics import BiometricError, BiometricUnavailable
from app.google_auth import GoogleAuthError, GoogleIdentity


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

    def audio_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool:
        self.strict_calls.append(strict)
        return stored == probe

    def face_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool:
        self.strict_calls.append(strict)
        return stored == probe


def _face_value(embedding: bytes) -> float | None:
    if not embedding.startswith(b"F:f"):
        return None
    try:
        return float(embedding[3:].split(b"-", 1)[0])
    except ValueError:
        return None


def fake_google_verifier(token: str) -> GoogleIdentity:
    """Tokens look like 'sub|email'; anything starting with 'bad' is rejected."""
    if token.startswith("bad"):
        raise GoogleAuthError("Invalid Google token")
    sub, email = token.split("|", 1)
    return GoogleIdentity(sub=sub, email=email)
