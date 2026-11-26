"""mcp_tool: call one tool of an MCP server the operator named, and nothing else.

AppCity's mcp_tools.py registered every tool a connected MCP client offered. Here nothing is discovered: the operator
lists the servers and the exact tools in the environment, and the model can only name one of those.

- MCP_TOOL_SERVERS = "name=https://host/path,other=https://host2/mcp" (empty means the tool is off);
- MCP_TOOL_ALLOWED = "name.tool,name.other_tool" (a server's tool that is not listed here is refused);
- the call is one JSON-RPC `tools/call` POST over streamable HTTP, through the same guard as http_tool (public
  addresses only, https, no redirects, size cap); the model supplies only the arguments, never a URL or a header.
"""

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from api.ai.agent import netguard

MAX_ARGUMENT_BYTES = 4000
MAX_TEXT = 8000


class McpError(ValueError):
    """The call is not allowed or failed; the message goes back to the model."""


@dataclass(frozen=True)
class McpResult:
    text: str
    is_error: bool
    truncated: bool


def servers() -> dict[str, str]:
    found: dict[str, str] = {}
    for entry in os.environ.get("MCP_TOOL_SERVERS", "").split(","):
        name, _, url = entry.strip().partition("=")
        if name.strip() and url.strip():
            found[name.strip()] = url.strip()
    return found


def allowed_tools() -> set[str]:
    return {t.strip() for t in os.environ.get("MCP_TOOL_ALLOWED", "").split(",") if t.strip()}


def _hosts(urls: dict[str, str]) -> set[str]:
    return {(urlsplit(url).hostname or "").lower().rstrip(".") for url in urls.values()} - {""}


def event_data(body: str) -> str:
    """A streamable HTTP server may answer as text/event-stream: the JSON-RPC message is in the `data:` lines."""
    datas = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
    return datas[-1] if datas else body


def call(server: str, tool: str, arguments: dict[str, Any]) -> McpResult:
    configured = servers()
    if not configured:
        raise McpError("mcp_tool is not enabled on this server")
    if server not in configured:
        raise McpError(f"Unknown server. Available: {', '.join(sorted(configured))}")
    if f"{server}.{tool}" not in allowed_tools():
        listed = sorted(t for t in allowed_tools() if t.startswith(server + "."))
        raise McpError(f"That tool is not allowed. Allowed: {', '.join(listed) or 'none'}")
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}).encode()
    if len(payload) > MAX_ARGUMENT_BYTES:
        raise McpError("The arguments are too large")
    try:
        fetched = netguard.post_json(configured[server], payload, _hosts(configured))
    except netguard.FetchError as error:
        raise McpError(str(error)) from None
    if fetched.status >= 400:
        raise McpError(f"The MCP server answered HTTP {fetched.status}")
    try:
        message = json.loads(event_data(fetched.body))
        result = message["result"] if "result" in message else None
    except (ValueError, TypeError):
        raise McpError("The MCP server's answer is not JSON-RPC") from None
    if not isinstance(result, dict):
        error = message.get("error") if isinstance(message, dict) else None
        raise McpError(f"The MCP server returned an error: {str((error or {}).get('message', 'unknown'))[:200]}")
    parts = [str(c.get("text", "")) for c in result.get("content", []) if isinstance(c, dict) and c.get("type") == "text"]
    text = "\n".join(parts)
    return McpResult(text[:MAX_TEXT], bool(result.get("isError")), len(text) > MAX_TEXT)
