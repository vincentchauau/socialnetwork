"""The shared agent's tools: what the model may ask the server to do for the user, and nothing else.

One toolbox for every app that lets a person talk to an assistant (Documents, Chat, Videos): the eight tools are AppCity's
(llm_tool, file_tool, web_tool, db_tool, http_tool, command_tool, mcp_tool) and the RAG one (rag_tool, with docs_tool to list
what can be searched), each rebuilt to be safe for a service with many users:

- the set is closed and written here; the model cannot add one, and an app picks which of them its assistant has;
- whose data is bound when the toolbox is built, from the session, in the app's `Scope`; no tool has a parameter that names a
  user, a path, a connection or a header, so the model cannot widen what it reaches;
- every argument is checked here (type, range, allowed values) before anything runs, whatever the model sent;
- what AppCity's tools did with a free hand is narrowed: file_tool reads only what the scope lists, db_tool queries a throwaway
  copy of the scope's own rows (sandbox_sql), http_tool, command_tool and mcp_tool refuse everything until the operator lists
  hosts, programs or servers (netguard, shell, mcp).

Tool results are data for the model to use, never instructions: the rules sent with them say so, and the citations an answer
makes are checked against the passages rag_tool actually returned.

What differs from one app to the next is the `Scope`: its passages (search), its list of documents, how one is read, and the
rows db_tool may see. An app writes a Scope; the tools, the planner and the limits are the same.
"""

import json
import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from api.ai.agent import mcp, netguard, sandbox_sql, shell
from api.ai.provider import AiProvider

import logging
logger = logging.getLogger(__name__)

PASSAGE_CHARS = 700
QUERY_MAX = 500
MAX_CALLS_PER_REQUEST = 10
LLM_TOKENS_DEFAULT = 512
LLM_TOKENS_MAX = 1024
WEB_RESULTS_DEFAULT = 5
WEB_RESULTS_MAX = 8
FILE_CHARS = 4000
FILE_MATCHES = 20
NAME_MAX = 255
TOP_K_DEFAULT = 5
TOP_K_MAX = 10


class ToolError(ValueError):
    """The arguments were not acceptable; the message goes back to the model, which may try again."""


@dataclass(frozen=True)
class ToolCall:
    """One use of a tool, as it is reported to the user (what was asked and how it went; never the data)."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    summary: str


class Passage(Protocol):
    """What a scope's search gives back (an app's own passage type fits as long as it has these)."""

    filename: str
    position: int
    text: str


class Scope(Protocol):
    """The data of one person in one app, as the shared tools reach it. An app writes one and nothing else."""

    #: The tables db_tool may query, as `{name: "column TYPE, ..."}` (the rows come from `snapshot`, in this column order).
    schema: dict[str, str]

    def search(self, query: str, top_k: int) -> Sequence[Passage]:
        """rag_tool: the passages that best answer `query`."""
        ...

    def documents(self) -> list[dict[str, Any]]:
        """docs_tool: what can be searched and read, as `{"name", "chunks", "characters"}`."""
        ...

    def read(self, name: str) -> str | None:
        """file_tool: the text of one of the documents by name, or None when there is none."""
        ...

    def snapshot(self) -> dict[str, list[tuple]]:
        """db_tool: the rows of each table of `schema` that the person may see."""
        ...


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # a JSON Schema object, as the model providers take it
    run: Callable[["ToolBox", dict[str, Any]], dict[str, Any]]


def text_arg(arguments: dict[str, Any], key: str, required: bool = False, limit: int = QUERY_MAX) -> str | None:
    try:
        value = arguments.get(key)
        if value is None or value == "":
            if required:
                raise ToolError(f"{key} is required")
            return None
        if not isinstance(value, str):
            raise ToolError(f"{key} must be text")
        value = value.strip()
        if not value and required:
            raise ToolError(f"{key} is required")
        if len(value) > limit:
            raise ToolError(f"{key} is longer than {limit} characters")
        return value or None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("text_arg failed")
        raise


def count_arg(arguments: dict[str, Any], key: str, default: int, maximum: int) -> int:
    try:
        value = arguments.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ToolError(f"{key} must be a whole number")
        if not 1 <= int(value) <= maximum:
            raise ToolError(f"{key} must be between 1 and {maximum}")
        return int(value)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("count_arg failed")
        raise


class ToolBox:
    """The tools of one request, bound to one person (through the scope). It also keeps the passages rag_tool returned, in the
    order they were numbered, so the answer's [n] markers can be checked against them."""

    def __init__(
        self,
        scope: Scope,
        provider: AiProvider | None = None,
        spend_model_call: Callable[[], None] | None = None,
        max_calls: int = MAX_CALLS_PER_REQUEST,
        tools: Collection[str] | None = None,
    ) -> None:
        try:
            self.scope = scope
            self.provider_seed_other = provider
            self._spend = spend_model_call or (lambda: None)  # called before llm_tool and web_tool use the model
            self._max_calls = max_calls
            self.passages: list[Passage] = []
            self.calls: list[ToolCall] = []
            every = tools_for(scope.schema)
            self.tools = {tool.name: tool for tool in every if tools is None or tool.name in tools}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    @property
    def declarations(self) -> list[dict[str, Any]]:
        try:
            return [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in self.tools.values()]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("declarations failed")
            raise

    def call(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        """Run a tool. A bad name or bad arguments come back as {"error": ...} for the model; nothing is raised."""
        arguments = arguments if isinstance(arguments, dict) else {}
        tool = self.tools.get(name)
        if tool is None:
            self.calls.append(ToolCall(name[:60], {}, False, "unknown tool"))
            return {"error": f"Unknown tool: {name[:60]}. Available: {', '.join(self.tools)}"}
        if len(self.calls) >= self._max_calls:
            self.calls.append(ToolCall(name, {}, False, "too many tool calls"))
            return {"error": f"Too many tool calls in one answer (at most {self._max_calls}); answer with what you have"}
        try:
            result = tool.run(self, arguments)
        except (ToolError, sandbox_sql.QueryError, netguard.FetchError, shell.CommandError, mcp.McpError) as error:
            self.calls.append(ToolCall(name, shown(arguments), False, str(error)[:200]))
            return {"error": str(error)[:300]}
        self.calls.append(ToolCall(name, shown(arguments), True, summary(result)))
        return result

    def model(self) -> AiProvider:
        try:
            if self.provider_seed_other is None:
                raise ToolError("No AI service is available for this tool")
            self._spend()
            return self.provider_seed_other
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("model failed")
            raise


def shown(arguments: dict[str, Any]) -> dict[str, Any]:
    """The arguments as the user sees them: short text and numbers only."""
    try:
        pairs = list(arguments.items())[:6]
        return {str(k)[:30]: (v[:80] if isinstance(v, str) else v) for k, v in pairs if isinstance(v, (str, int, float)) and not isinstance(v, bool)}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("shown failed")
        raise


def summary(result: dict[str, Any]) -> str:
    try:
        if "exit_code" in result:
            return f"exit {result['exit_code']}"
        if "status" in result and "body" in result:
            return f"HTTP {result['status']}"
        if "text" in result and "count" not in result and "name" not in result:
            return f"{len(result['text'])} characters"
        if "text" in result:
            return f"{result.get('characters', 0)} characters"
        return f"{result.get('count', 0)} found"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("summary failed")
        raise


def schema_of(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    try:
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("schema_of failed")
        raise


# -- the tools ------------------------------------------------------------------------------------------------
def rag_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        query = text_arg(arguments, "query", required=True)
        top_k = count_arg(arguments, "top_k", TOP_K_DEFAULT, TOP_K_MAX)
        numbered = []
        for passage in box.scope.search(query or "", top_k):
            box.passages.append(passage)
            numbered.append(
                {
                    "n": len(box.passages),  # the number to cite, counted over every search of this request
                    "document": passage.filename,
                    "position": passage.position + 1,
                    "text": passage.text[:PASSAGE_CHARS],
                }
            )
        return {"count": len(numbered), "passages": numbered}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("rag_tool failed")
        raise


def docs_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        documents = box.scope.documents()
        return {"count": len(documents), "documents": documents}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("docs_tool failed")
        raise


def llm_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    """A second, tool-less call of the model for a sub-task (summarize, translate, rewrite some text)."""
    try:
        prompt = text_arg(arguments, "prompt", required=True, limit=4000)
        tokens = count_arg(arguments, "max_tokens", LLM_TOKENS_DEFAULT, LLM_TOKENS_MAX)
        return {"text": box.model().generate(prompt or "", tokens)}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("llm_tool failed")
        raise


def web_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    """Search the public web through the model provider's own search; this server fetches no page itself."""
    try:
        query = text_arg(arguments, "query", required=True)
        results = count_arg(arguments, "max_results", WEB_RESULTS_DEFAULT, WEB_RESULTS_MAX)
        found = box.model().web_search(query or "", results)
        return {"count": len(found.get("sources", [])), **found}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("web_tool failed")
        raise


def file_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    """Read one of the person's own documents, or search its lines for words. It reaches no other file."""
    try:
        name = text_arg(arguments, "name", required=True, limit=NAME_MAX)
        query = text_arg(arguments, "query", limit=200)
        text = box.scope.read(name or "")
        if text is None:
            raise ToolError("No document with that name; docs_tool lists the names")
        if not query:
            return {"name": name, "characters": len(text), "text": text[:FILE_CHARS], "truncated": len(text) > FILE_CHARS}
        words = re.findall(r"\w+", query.lower())
        if not words:
            raise ToolError("query has no words")
        matches = [{"line": number, "text": line[:300]} for number, line in enumerate(text.split("\n"), start=1) if all(word in line.lower() for word in words)]
        return {"name": name, "count": len(matches[:FILE_MATCHES]), "matches": matches[:FILE_MATCHES], "truncated": len(matches) > FILE_MATCHES}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("file_tool failed")
        raise


def db_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    """A SELECT on a throwaway copy of the person's own data (never on the real database)."""
    try:
        query = text_arg(arguments, "query", required=True, limit=sandbox_sql.QUERY_MAX)
        limit = count_arg(arguments, "limit", sandbox_sql.ROW_LIMIT_DEFAULT, sandbox_sql.ROW_LIMIT_MAX)
        result = sandbox_sql.run_query(box.scope.snapshot(), query or "", limit, box.scope.schema)
        return {"columns": result.columns, "rows": result.rows, "count": len(result.rows), "truncated": result.truncated}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("db_tool failed")
        raise


def http_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    """One GET or HEAD to a host the operator allowed (none by default)."""
    try:
        url = text_arg(arguments, "url", required=True, limit=netguard.MAX_URL)
        method = (text_arg(arguments, "method", limit=8) or "GET").upper()
        fetched = netguard.fetch(url or "", method)
        return {"status": fetched.status, "content_type": fetched.content_type, "body": fetched.body, "truncated": fetched.truncated}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("http_tool failed")
        raise


def command_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    """One program the operator allowed, run without a shell (none by default)."""
    try:
        command = arguments.get("command")
        if command is None or command == "":
            raise ToolError("command is required")
        timeout = count_arg(arguments, "timeout", shell.TIMEOUT_DEFAULT, shell.TIMEOUT_MAX)
        ran = shell.run(command, timeout)
        return {"exit_code": ran.exit_code, "stdout": ran.stdout, "stderr": ran.stderr, "truncated": ran.truncated}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("command_tool failed")
        raise


def mcp_tool(box: ToolBox, arguments: dict[str, Any]) -> dict[str, Any]:
    """One tool of an MCP server the operator named and allowed (none by default)."""
    server = text_arg(arguments, "server", required=True, limit=60)
    tool = text_arg(arguments, "tool", required=True, limit=80)
    raw = text_arg(arguments, "input", limit=mcp.MAX_ARGUMENT_BYTES) or "{}"
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise ToolError("input must be a JSON object, like {\"query\": \"x\"}") from None
    if not isinstance(parsed, dict):
        raise ToolError("input must be a JSON object")
    result = mcp.call(server or "", tool or "", parsed)
    return {"text": result.text, "is_error": result.is_error, "truncated": result.truncated}


def text_tools() -> tuple[Tool, ...]:
    """The tools that read the user's documents, ask the model and search the web."""
    try:
        return (
            Tool(
                "rag_tool",
                "Search the user's own documents. Returns the best matching passages, each with a number n to cite as [n] in the "
                "answer. Search by meaning and by words together; the question may be in any language.",
                schema_of(
                    {
                        "query": {"type": "string", "description": "What to look for, in the user's words."},
                        "top_k": {"type": "integer", "description": f"How many passages, 1 to {TOP_K_MAX}. Default {TOP_K_DEFAULT}."},
                    },
                    ["query"],
                ),
                rag_tool,
            ),
            Tool("docs_tool", "List the documents the user has added (name, number of chunks). Use it to see what can be searched.", schema_of({}), docs_tool),
            Tool(
                "llm_tool",
                "Ask the language model for a sub-task on text you give it (summarize, translate, rewrite, extract). It has no tools "
                "and no access to the user's data except what is in the prompt.",
                schema_of(
                    {
                        "prompt": {"type": "string", "description": "The task and the text to work on."},
                        "max_tokens": {"type": "integer", "description": f"Length of the reply, 1 to {LLM_TOKENS_MAX}. Default {LLM_TOKENS_DEFAULT}."},
                    },
                    ["prompt"],
                ),
                llm_tool,
            ),
            Tool(
                "web_tool",
                "Search the public web for current information. Returns a short answer and the sources it used.",
                schema_of(
                    {
                        "query": {"type": "string", "description": "What to search for."},
                        "max_results": {"type": "integer", "description": f"How many sources, 1 to {WEB_RESULTS_MAX}. Default {WEB_RESULTS_DEFAULT}."},
                    },
                    ["query"],
                ),
                web_tool,
            ),
            Tool(
                "file_tool",
                "Read one of the user's own documents by name (the first part of it), or find the lines of it that hold all the "
                "given words. docs_tool lists the names. No other file can be read.",
                schema_of(
                    {
                        "name": {"type": "string", "description": "The document name, as docs_tool gives it."},
                        "query": {"type": "string", "description": "Words that every returned line must contain. Leave out to read the document."},
                    },
                    ["name"],
                ),
                file_tool,
            ),
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("text_tools failed")
        raise


def system_tools(schema: dict[str, str]) -> tuple[Tool, ...]:
    """The tools that read the user's data (a copy), the network and the programs the operator allows."""
    try:
        return (
            Tool(
                "db_tool",
                "Run one read-only SQL SELECT on a copy of the user's own data. Tables: " + sandbox_sql.describe(schema) + ". Use it to count "
                "and total things (how many items, how many views, what is about to expire).",
                schema_of(
                    {
                        "query": {"type": "string", "description": "One SELECT (or WITH ... SELECT) statement."},
                        "limit": {"type": "integer", "description": f"Rows to return, 1 to {sandbox_sql.ROW_LIMIT_MAX}. Default {sandbox_sql.ROW_LIMIT_DEFAULT}."},
                    },
                    ["query"],
                ),
                db_tool,
            ),
            Tool(
                "http_tool",
                "Fetch a text page or a JSON document with one GET from a host the operator allowed. Most addresses are refused; "
                "the error lists the allowed hosts. Redirects are not followed.",
                schema_of(
                    {
                        "url": {"type": "string", "description": "The full https URL."},
                        "method": {"type": "string", "enum": ["GET", "HEAD"], "description": "GET (default) or HEAD."},
                    },
                    ["url"],
                ),
                http_tool,
            ),
            Tool(
                "command_tool",
                "Run one program the operator allowed, without a shell (no pipes or redirects). Disabled unless the operator lists "
                "programs; the error says which are allowed.",
                schema_of(
                    {
                        "command": {"type": "string", "description": "The program and its arguments, like: date +%Y."},
                        "timeout": {"type": "integer", "description": f"Seconds before it is stopped, 1 to {shell.TIMEOUT_MAX}. Default {shell.TIMEOUT_DEFAULT}."},
                    },
                    ["command"],
                ),
                command_tool,
            ),
            Tool(
                "mcp_tool",
                "Call one tool of an MCP server the operator allowed. Disabled unless the operator lists servers; the error says "
                "which server and tools are allowed.",
                schema_of(
                    {
                        "server": {"type": "string", "description": "The server name."},
                        "tool": {"type": "string", "description": "The tool name on that server."},
                        "input": {"type": "string", "description": "The tool's arguments as a JSON object text, like {\"query\": \"x\"}."},
                    },
                    ["server", "tool"],
                ),
                mcp_tool,
            ),
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("system_tools failed")
        raise


def tools_for(schema: dict[str, str]) -> tuple[Tool, ...]:
    """Every tool, described for a scope whose db_tool can read the tables in `schema`."""
    try:
        return text_tools() + system_tools(schema)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("tools_for failed")
        raise


