"""Voice and face biometrics. Heavy libraries (numpy, resemblyzer, opencv, face_recognition,
ffmpeg) are imported lazily so center runs and is testable without them.

Embeddings are opaque `bytes` (float32 vectors) so the core never needs numpy.
"""

import functools
import logging
import math
from typing import Callable, Protocol, TypeVar

from api.center.config import Settings

audit = logging.getLogger("auth.audit")
T = TypeVar("T")
NO_SIMILARITY = -1.0  # below any threshold: what malformed or unusable data scores


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
    def audio_similarity(self, stored: bytes, probe: bytes) -> float: ...
    def audio_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool: ...
    def face_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool: ...


class RealBiometrics:
    """resemblyzer for voices, face_recognition for faces."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    @engine_guard
    def audio_embedding(self, raw: bytes) -> bytes:
        from api.center.biometrics.audio import embed_audio

        return embed_audio(raw, self._s.ffmpeg_timeout)

    @engine_guard
    def face_embedding(self, raw: bytes) -> bytes:
        from api.center.biometrics.video import embed_face

        return embed_face(raw, self._s.max_frames)

    def audio_similarity(self, stored: bytes, probe: bytes) -> float:
        """Cosine similarity; malformed, mismatched or zero-norm data is "no match" (-1.0), never an error."""
        import numpy as np

        width = np.dtype(np.float32).itemsize
        if not stored or len(stored) % width or len(probe) % width:
            return NO_SIMILARITY
        template, sample = np.frombuffer(stored, np.float32), np.frombuffer(probe, np.float32)
        if template.shape != sample.shape:  # corrupt or different model
            return NO_SIMILARITY
        denom = float(np.linalg.norm(template) * np.linalg.norm(sample))
        if not denom or not math.isfinite(denom):
            return NO_SIMILARITY
        return float(np.dot(template, sample) / denom)

    def audio_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool:
        return self.audio_similarity(stored, probe) >= (
            self._s.audio_threshold_alone if strict else self._s.audio_threshold
        )

    def face_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool:
        import numpy as np

        width = np.dtype(np.float32).itemsize
        if not stored or not probe or len(stored) % width or len(probe) % width:
            return False
        template, sample = np.frombuffer(stored, np.float32), np.frombuffer(probe, np.float32)
        if template.shape != sample.shape:
            return False
        limit = self._s.face_threshold_alone if strict else self._s.face_threshold
        return float(np.linalg.norm(template - sample)) <= limit

    def liveness_actions(self, raw: bytes) -> list[str]:
        """Ordered actions seen in a webcam clip; [] on any problem (never raises). See app.liveness."""
        from api.center.biometrics.liveness_video import liveness_actions

        return liveness_actions(raw)

    def face_distance(self, stored: bytes, probe: bytes) -> float:
        import numpy as np

        # Corrupt or placeholder data is "infinitely far", never an exception: this runs for every
        # candidate on a login attempt, so a 500 here would be reachable by anyone.
        width = np.dtype(np.float32).itemsize
        if not stored or not probe or len(stored) % width or len(probe) % width:
            return float("inf")
        template, sample = np.frombuffer(stored, np.float32), np.frombuffer(probe, np.float32)
        if template.shape != sample.shape:
            return float("inf")
        return float(np.linalg.norm(template - sample))
