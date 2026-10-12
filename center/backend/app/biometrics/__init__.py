"""Voice and face biometrics. Heavy libraries (numpy, resemblyzer, opencv, face_recognition,
ffmpeg) are imported lazily so center runs and is testable without them.

Embeddings are opaque `bytes` (float32 vectors) so the core never needs numpy.
"""

import functools
import logging
from typing import Callable, Protocol, TypeVar

from app.config import Settings

audit = logging.getLogger("auth.audit")
T = TypeVar("T")


class BiometricError(ValueError):
    """The sample is unusable (empty, corrupt, no face or voice found...)."""


class BiometricUnavailable(RuntimeError):
    """A required library or tool is missing or broken (ffmpeg, face_recognition, resemblyzer...)."""


def engine_guard(embed: Callable[..., T]) -> Callable[..., T]:
    """A crashing native library is a server-side outage (503), never a 500 and never the user's fault.

    Only the exception type is logged: the message could contain paths or sample data.
    """

    @functools.wraps(embed)
    def wrapper(*args, **kwargs) -> T:
        try:
            return embed(*args, **kwargs)
        except (BiometricError, BiometricUnavailable):
            raise
        except Exception as exc:
            audit.error("biometric engine failure: %s", type(exc).__name__)
            raise BiometricUnavailable("Biometric engine failed") from exc

    return wrapper


class Biometrics(Protocol):
    def audio_embedding(self, raw: bytes) -> bytes: ...
    def face_embedding(self, raw: bytes) -> bytes: ...
    def face_distance(self, stored: bytes, probe: bytes) -> float: ...
    def audio_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool: ...
    def face_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool: ...


class RealBiometrics:
    """resemblyzer for voices, face_recognition for faces."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    @engine_guard
    def audio_embedding(self, raw: bytes) -> bytes:
        from app.biometrics.audio import embed_audio

        return embed_audio(raw, self._s.ffmpeg_timeout)

    @engine_guard
    def face_embedding(self, raw: bytes) -> bytes:
        from app.biometrics.video import embed_face

        return embed_face(raw, self._s.max_frames)

    def audio_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool:
        import numpy as np

        template, sample = np.frombuffer(stored, np.float32), np.frombuffer(probe, np.float32)
        if template.shape != sample.shape:  # corrupt or different model: a non-match, not a 500
            return False
        denom = float(np.linalg.norm(template) * np.linalg.norm(sample))
        similarity = float(np.dot(template, sample) / denom) if denom else 0.0
        return similarity >= (self._s.audio_threshold_alone if strict else self._s.audio_threshold)

    def face_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool:
        import numpy as np

        template, sample = np.frombuffer(stored, np.float32), np.frombuffer(probe, np.float32)
        if template.shape != sample.shape:
            return False
        limit = self._s.face_threshold_alone if strict else self._s.face_threshold
        return float(np.linalg.norm(template - sample)) <= limit

    def face_distance(self, stored: bytes, probe: bytes) -> float:
        import numpy as np

        template, sample = np.frombuffer(stored, np.float32), np.frombuffer(probe, np.float32)
        if template.shape != sample.shape:
            return float("inf")
        return float(np.linalg.norm(template - sample))
