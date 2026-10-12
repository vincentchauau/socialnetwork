"""Voice and face biometrics. Heavy libraries (numpy, resemblyzer, opencv, face_recognition,
ffmpeg) are imported lazily so center runs and is testable without them.

Embeddings are opaque `bytes` (float32 vectors) so the core never needs numpy.
"""

from typing import Protocol

from app.config import Settings


class BiometricError(ValueError):
    """The sample is unusable (empty, corrupt, no face or voice found...)."""


class BiometricUnavailable(RuntimeError):
    """A required library or tool is missing (ffmpeg, face_recognition, resemblyzer)."""


class Biometrics(Protocol):
    def audio_embedding(self, raw: bytes) -> bytes: ...
    def face_embedding(self, raw: bytes) -> bytes: ...
    def audio_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool: ...
    def face_matches(self, stored: bytes, probe: bytes, strict: bool = False) -> bool: ...


class RealBiometrics:
    """resemblyzer for voices, face_recognition for faces."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def audio_embedding(self, raw: bytes) -> bytes:
        from app.biometrics.audio import embed_audio

        return embed_audio(raw, self._s.ffmpeg_timeout)

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
