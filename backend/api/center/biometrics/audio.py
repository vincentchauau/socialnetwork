"""Voice: any audio -> 16 kHz mono wav via ffmpeg (with timeout) -> resemblyzer embedding."""

import io
import shutil
import subprocess  # nosec B404 - only runs ffmpeg with fixed arguments; user data goes via stdin
import threading
import wave
from functools import lru_cache

from api.center.biometrics import BiometricError, BiometricUnavailable

SAMPLE_RATE = 16000
MAX_SECONDS = 10
encoder_lock = threading.Lock()


@lru_cache(maxsize=1)
def build_encoder():
    try:
        from resemblyzer import VoiceEncoder
    except ImportError as exc:
        raise BiometricUnavailable("resemblyzer is not installed") from exc
    return VoiceEncoder()


def _encoder():
    with encoder_lock:  # lru_cache does not lock: load the model exactly once
        return build_encoder()


def to_wav_bytes(raw: bytes, timeout: int) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise BiometricUnavailable("ffmpeg is not installed")
    try:
        result = subprocess.run(  # nosec B603 - resolved path, fixed args, no shell
            [ffmpeg, "-v", "error", "-protocol_whitelist", "pipe", "-i", "pipe:0", "-vn",
             "-t", str(MAX_SECONDS), "-f", "wav", "-acodec", "pcm_s16le", "-ac", "1",
             "-ar", str(SAMPLE_RATE), "pipe:1"],
            input=raw, capture_output=True, timeout=timeout, check=False,
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        raise BiometricError("Audio processing took too long") from exc
    if result.returncode != 0 or not result.stdout:
        raise BiometricError("Could not read the audio")
    return result.stdout


def wav_to_floats(wav_bytes: bytes):
    import numpy as np

    try:
        with wave.open(io.BytesIO(wav_bytes)) as handle:
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise BiometricError("Invalid wav data") from exc
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size < SAMPLE_RATE // 2:
        raise BiometricError("Recording is too short")
    return samples


def embed_audio(raw: bytes, timeout: int) -> bytes:
    import numpy as np

    encoder = _encoder()  # check the library before spending time on ffmpeg
    try:
        from resemblyzer import preprocess_wav
    except ImportError as exc:
        raise BiometricUnavailable("resemblyzer is not installed") from exc
    wav = preprocess_wav(wav_to_floats(to_wav_bytes(raw, timeout)))
    return np.asarray(encoder.embed_utterance(wav), dtype=np.float32).tobytes()
