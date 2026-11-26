from sn_shared.deps import access_dependencies
"""The shared agent as a service of an app: one function that answers a question with the tools of a scope, and one that mounts
`POST /ai/agent` for an app (Documents, Chat, Videos: each writes a `Scope` and a few lines, the rest is here).

Two limits keep a real model affordable, per person and per hour, in this process (a restart forgets them): the questions
asked (AI_AGENT_HOURLY_LIMIT) and the model sub-calls the tools make (AI_TOOL_HOURLY_LIMIT: llm_tool and web_tool).
"""

import os
import re
import time
from collections.abc import Callable, Collection
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session

from api.ai.agent import planner
from api.ai.agent.toolbox import Scope, ToolBox, ToolError
from api.ai.provider import AiProvider
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

import logging
logger = logging.getLogger(__name__)

QUESTION_MAX = 500
DEFAULT_AGENT_HOURLY_LIMIT = 30
DEFAULT_TOOL_HOURLY_LIMIT = 40
HOUR_SECONDS = 3600
CITATION = re.compile(r"\[(\d{1,3})\]")


class AgentIn(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX)]
    mode: Literal["tools", "plan"] = "tools"  # "plan": write a plan first, run it, then answer (planner.py)


class PlanStepOut(BaseModel):
    id: str
    tool: str
    params: dict[str, Any]


class ToolCallOut(BaseModel):
    name: str
    arguments: dict[str, Any]
    ok: bool
    summary: str


class SourceOut(BaseModel):
    """A passage the answer may cite as [n] (its place in `sources`, from 1). What an index knows beyond the text is optional."""

    filename: str
    position: int
    text: str
    doc_id: int | None = None
    score: float | None = None
    dense_rank: int | None = None
    lexical_rank: int | None = None


class AgentOut(BaseModel):
    language: str
    content: str
    is_dummy: bool
    sources: list[SourceOut] = Field(default_factory=list)
    cited: list[int] = Field(default_factory=list)  # the [n] of `sources` the answer relies on
    invented_citations: int = 0  # markers that pointed at nothing retrieved; they are removed from `content`
    plan: list[PlanStepOut] = Field(default_factory=list)  # the steps run in plan mode
    tool_calls: list[ToolCallOut] = Field(default_factory=list)  # which tools were used, with what, and how it went


def check_citations(content: str, available: int) -> tuple[str, list[int], int]:
    """Keep only the [n] markers that point at one of the `available` passages.

    Returns the text without the invented markers, the sorted valid numbers that were cited, and how many markers were invented.
    An answer may cite what was retrieved and nothing else (no semantic entailment check: existence is what can be verified).
    """
    try:
        cited: set[int] = set()
        invented = 0

        def keep(match: re.Match[str]) -> str:
            try:
                nonlocal invented
                number = int(match.group(1))
                if 1 <= number <= available:
                    cited.add(number)
                    return match.group(0)
                invented += 1
                return ""
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("keep failed")
                raise

        return CITATION.sub(keep, content), sorted(cited), invented
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("check_citations failed")
        raise


class Limits:
    """At most so many questions, and so many model sub-calls of tools, per person per hour."""

    def __init__(self, questions: int | None = None, model_calls: int | None = None) -> None:
        try:
            self.questions = questions if questions is not None else int(os.environ.get("AI_AGENT_HOURLY_LIMIT", DEFAULT_AGENT_HOURLY_LIMIT))
            self.model_calls = model_calls if model_calls is not None else int(os.environ.get("AI_TOOL_HOURLY_LIMIT", DEFAULT_TOOL_HOURLY_LIMIT))
            self._asked: dict[int, list[float]] = {}
            self._spent: dict[int, list[float]] = {}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    @staticmethod
    def take_service(book: dict[int, list[float]], user_id: int, limit: int) -> bool:
        try:
            now = time.monotonic()
            times = [t for t in book.get(user_id, []) if now - t < HOUR_SECONDS]
            if len(times) >= limit:
                book[user_id] = times
                return False
            book[user_id] = [*times, now]
            return True
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("take_service failed")
            raise

    def ask(self, user_id: int) -> None:
        try:
            if not self.take_service(self._asked, user_id, self.questions):
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many questions this hour; try again later")
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("ask failed")
            raise

    def spend(self, user_id: int) -> Callable[[], None]:
        """What the toolbox calls before llm_tool and web_tool use the model."""

        try:
            def take() -> None:
                try:
                    if not self.take_service(self._spent, user_id, self.model_calls):
                        raise ToolError("Too many model sub-calls this hour; answer without it")
                except Exception as error:
                    if getattr(error, "status_code", None) is None:
                        logger.exception("take failed")
                    raise

            return take
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("spend failed")
            raise


def source_of(passage: Any) -> SourceOut:
    try:
        return SourceOut(
            filename=passage.filename,
            position=passage.position,
            text=passage.text,
            doc_id=getattr(passage, "doc_id", None),
            score=getattr(passage, "score", None),
            dense_rank=getattr(passage, "dense_rank", None),
            lexical_rank=getattr(passage, "lexical_rank", None),
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("source_of failed")
        raise


def answer(question: str, mode: str, scope: Scope, provider: AiProvider, spend: Callable[[], None] | None = None, tools: Collection[str] | None = None) -> AgentOut:
    """Answer `question` with the tools of `scope`: the model calls them as it needs (mode "tools"), or writes a plan first (mode "plan")."""
    try:
        toolbox = ToolBox(scope, provider, spend, tools=tools)
        steps: list[planner.Step] = []
        if mode == "plan":
            reply, steps = planner.run_plan(question, toolbox, provider)
        else:
            reply = provider.run_agent(question, toolbox)
        content, cited, invented = check_citations(reply.content, len(toolbox.passages))
        return AgentOut(
            language=reply.language,
            content=content,
            is_dummy=provider.is_dummy,
            sources=[source_of(passage) for passage in toolbox.passages],
            cited=cited,
            invented_citations=invented,
            plan=[PlanStepOut(id=s.id, tool=s.tool, params=s.params) for s in steps],
            tool_calls=[ToolCallOut(name=c.name, arguments=c.arguments, ok=c.ok, summary=c.summary) for c in toolbox.calls],
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("answer failed")
        raise


def mount(
    app: FastAPI,
    get_db: Callable[..., Any],
    scope_for: Callable[[Request, Session, TokenPayload], Scope],
    tools: Collection[str] | None = None,
    path: str = "/ai/agent",
) -> Limits:
    """Add `POST <path>` (and the way a refused tool call is told) to an app. `scope_for` says whose data the tools reach: it is built
    from the session only, so nothing the caller sends can widen it. `app.state.ai` is the provider. Returns the limits (tests change them)."""
    try:
        limits = Limits()

        @app.exception_handler(ToolError)
        async def tool_failed(_request: Request, error: ToolError) -> JSONResponse:
            try:
                return JSONResponse({"detail": str(error)}, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("tool_failed failed")
                raise

        @app.post(path, response_model=AgentOut, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        def ask_agent(
            request: Request,
            body: AgentIn,
            user: Annotated[TokenPayload, Depends(get_current_user)],
            db: Annotated[Session, Depends(get_db)],
        ) -> AgentOut:
            try:
                limits.ask(user.user_id)
                return answer(body.question, body.mode, scope_for(request, db, user), request.app.state.ai, limits.spend(user.user_id), tools)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("ask_agent failed")
                raise

        return limits
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("mount failed")
        raise
