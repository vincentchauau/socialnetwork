"""The AI behind the video studio and the assistant, behind one small interface.

Two providers: `dummy` answers from the prompt alone, deterministically, with no network, no key and no cost (the
screens, the limits and the tests run on it), and `gemini` (app/gemini.py) calls Google's Gemini for embeddings, answers
and video scripts. AI_PROVIDER chooses; any other value, or gemini without a key, fails at startup instead of silently
falling back to the dummy. The picture and voice of a video (blueskyartist used ffmpeg with gTTS) are not rendered yet.

The assistant never runs commands and never touches the database: blueskyartist's agent returned SQL and shell
snippets for a developer to run, which must not be offered to users of a web app.
"""

import hashlib
import math
import os
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

SCENES = 8


class AiError(RuntimeError):
    """The AI provider could not do what was asked (a network error, a refusal, an unreadable answer)."""


SCENE_SECONDS = 8
SLUG_WORDS = 8
EMBEDDING_DIMENSIONS = 1024  # more slots, fewer collisions between unrelated words
PASSAGE_PREVIEW = 240


@dataclass(frozen=True)
class Subtitle:
    language: str
    text: str


@dataclass(frozen=True)
class VideoScript:
    topic: str
    filename: str
    stories: tuple[str, ...]
    subtitles: tuple[Subtitle, ...]


@dataclass(frozen=True)
class AgentAnswer:
    language: str
    content: str


class Toolbox(Protocol):
    """What a provider may use while it answers: the tools it can call and a way to call them (app/tools.py)."""

    @property
    def declarations(self) -> list[dict]: ...

    def call(self, name: str, arguments: dict | None) -> dict: ...


class AiProvider(Protocol):
    name: str
    is_dummy: bool
    min_similarity: float  # the cosine below which two embeddings are not "about the same thing"

    def video_script(self, prompt: str) -> VideoScript: ...

    def answer(self, question: str, passages: Sequence[str] = ()) -> AgentAnswer: ...

    def embed(self, texts: Sequence[str], purpose: str = "document") -> list[list[float]]: ...

    def run_agent(self, question: str, toolbox: Toolbox) -> AgentAnswer: ...

    def generate(self, prompt: str, max_tokens: int) -> str: ...

    def web_search(self, query: str, max_results: int) -> dict: ...


def words_provider(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    ascii_text = folded.encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+", ascii_text)


def timestamp(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d},000"


SHOTS = (
    "wide establishing shot",
    "slow push-in",
    "low angle",
    "over-the-shoulder",
    "close-up",
    "tracking shot",
    "overhead",
    "slow pull-out",
)


class DummyProvider:
    """Deterministic stand-in: the same prompt always gives the same script."""

    name = "dummy"
    is_dummy = True
    min_similarity = 0.25  # one shared word of a short question gives about 0.3; a lone collision is rare at this size

    def video_script(self, prompt: str) -> VideoScript:
        words = words_provider(prompt) or ["untitled"]
        slug = "_".join(words[:SLUG_WORDS])
        stories = tuple(
            f"[CAMERA: {SHOTS[n % len(SHOTS)]}] [VISUALS: scene {n + 1} of {SCENES} about \"{prompt.strip()}\"] "
            f"[AUDIO: Narrator says: \"Scene {n + 1}.\"]"
            for n in range(SCENES)
        )
        blocks = [
            f"{n + 1}\n{timestamp(n * SCENE_SECONDS)} --> {timestamp((n + 1) * SCENE_SECONDS)}\nScene {n + 1}: {prompt.strip()}"
            for n in range(SCENES)
        ]
        return VideoScript(topic=slug, filename=slug, stories=stories, subtitles=(Subtitle("en", "\n\n".join(blocks)),))

    def answer(self, question: str, passages: Sequence[str] = ()) -> AgentAnswer:
        if passages:
            quoted = "\n".join(f"- [{n}] {text[:PASSAGE_PREVIEW].strip()}" for n, text in enumerate(passages, start=1))
            return AgentAnswer(
                language="text",
                content=(
                    "Đây là câu trả lời giả lập: trợ lý chưa nối với mô hình AI nào, nên chỉ trích các đoạn "
                    f"liên quan nhất trong tài liệu của bạn cho câu hỏi \"{question.strip()}\":\n{quoted}"
                ),
            )
        return AgentAnswer(
            language="text",
            content=(
                "Đây là câu trả lời giả lập: trợ lý chưa nối với mô hình AI nào "
                "và bạn chưa thêm tài liệu nào để tra cứu. "
                f"Bạn vừa hỏi: \"{question.strip()}\""
            ),
        )

    def run_agent(self, question: str, toolbox: Toolbox) -> AgentAnswer:
        """The dummy has no judgement, so it always does the same thing: search the documents with rag_tool, then quote."""
        found = toolbox.call("rag_tool", {"query": question, "top_k": 5})
        return self.answer(question, [passage["text"] for passage in found.get("passages", [])])

    def generate(self, prompt: str, max_tokens: int) -> str:
        return "Đây là bản giả lập (chưa có mô hình AI), nên chưa thể xử lý yêu cầu này."

    def web_search(self, query: str, max_results: int) -> dict:
        return {"answer": "Tìm web chưa có trong bản giả lập: chưa nối với dịch vụ tìm kiếm nào.", "sources": []}

    def embed(self, texts: Sequence[str], purpose: str = "document") -> list[list[float]]:
        """Hash every word into one of EMBEDDING_DIMENSIONS slots (with a sign), then normalize: same words, same vector."""
        vectors = []
        for text in texts:
            vector = [0.0] * EMBEDDING_DIMENSIONS
            for word in words_provider(text):
                digest = hashlib.md5(word.encode("utf-8"), usedforsecurity=False).digest()
                slot = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
                vector[slot] += 1.0 if digest[4] % 2 == 0 else -1.0
            norm = math.sqrt(sum(x * x for x in vector))
            vectors.append([x / norm for x in vector] if norm else vector)
        return vectors


def get_provider() -> AiProvider:
    name = os.environ.get("AI_PROVIDER", "dummy").strip().lower() or "dummy"
    if name == "dummy":
        return DummyProvider()
    if name == "gemini":
        from api.ai.gemini import GeminiProvider

        key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("AI_PROVIDER=gemini needs GEMINI_API_KEY (or GOOGLE_API_KEY)")
        return GeminiProvider(key)
    raise RuntimeError(f"AI_PROVIDER={name!r} is not supported; use 'dummy' or 'gemini'")
