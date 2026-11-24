"""Speech, both ways, with the model of the platform (Gemini, with the key of `GEMINI_API_KEY` / `GOOGLE_API_KEY`).

What a person says in a call, or to the voice button of the room, is made into words (`transcribe`, `STT_MODEL`): that sound goes to the model and
nothing of it is kept. What a virtual person answers becomes sound (`synthesize`, `TTS_MODEL`). Without the key nothing is heard and nothing is said
aloud (what was typed or answered is still written)."""

import base64
import io
import json
import logging
import os
import urllib.error
import urllib.request
import wave

log = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_STT_MODEL = "gemini-3.5-flash"
DEFAULT_TTS_MODEL = "gemini-3.8-flash-tts"
TTS_RATE = 24000
TIMEOUT_SECONDS = 40
MAX_SPOKEN_CHARS = 600
HEARD_PROMPT = (
    "Transcribe the speech in this audio exactly as spoken, in the language spoken (Vietnamese or English). "
    "Answer with the words only. If there is no clear human speech, answer with an empty text."
)
VOICES = ("Kore", "Puck", "Zephyr", "Charon", "Leda", "Aoede", "Fenrir", "Orus")


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def enabled() -> bool:
    return bool(api_key())


def _post(model: str, body: dict) -> dict:
    request = urllib.request.Request(
        f"{BASE_URL}/models/{model}:generateContent", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key()},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - the model of the platform
        return json.loads(response.read())


def _wav(pcm: bytes, rate: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(pcm)
    return out.getvalue()


def transcribe(pcm: bytes, rate: int) -> str:
    """The words in PCM16 mono sound ("" when there are none, or the model cannot be reached)."""
    if not enabled() or not pcm:
        return ""
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(_wav(pcm, rate)).decode()}}, {"text": HEARD_PROMPT}]}]}
    try:
        data = _post(os.environ.get("STT_MODEL", DEFAULT_STT_MODEL), body)
        return str(data["candidates"][0]["content"]["parts"][0].get("text", "")).strip()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError):
        log.warning("the speech could not be turned into text", exc_info=True)
        return ""


def voice_of(username: str) -> str:
    return VOICES[sum(username.encode()) % len(VOICES)]


def synthesize(text: str, voice: str) -> tuple[bytes, int] | None:
    """The voice of `text` as PCM16 mono and its rate, or None when it cannot be made."""
    if not enabled() or not text.strip():
        return None
    body = {
        "contents": [{"parts": [{"text": text.strip()[:MAX_SPOKEN_CHARS]}]}],
        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
    }
    try:
        data = _post(os.environ.get("TTS_MODEL", DEFAULT_TTS_MODEL), body)
        return base64.b64decode(data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]), TTS_RATE
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError):
        log.warning("the words could not be turned into a voice", exc_info=True)
        return None
