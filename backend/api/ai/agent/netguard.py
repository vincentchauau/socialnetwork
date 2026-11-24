"""http_tool's network access: one GET to a host the operator allowed, and to no other place.

AppCity's http_tool called any URL with any method and headers. A server that does that for a model is a way into its
own network (cloud metadata, other containers, the database), so this one is closed by default and, when opened:

- only hosts named in HTTP_TOOL_ALLOWED_HOSTS (a comma list) are reachable; empty means the tool is off;
- https only (http when HTTP_TOOL_ALLOW_HTTP=1, for a test), ports 443 and 80;
- the host is resolved here and every address must be public (no loopback, private, link-local, reserved, multicast);
  the connection goes to the address that was checked, with the hostname used for the certificate, so a name that
  changes its answer between the check and the connection cannot reach an inside address;
- GET and HEAD only, no body, no headers of the caller's, no cookies, no redirects (a redirect is a different host);
- a short timeout, and the answer is cut at a small size and only text types are returned.
"""

import http.client
import ipaddress
import os
import socket
import ssl
import urllib.parse
from dataclasses import dataclass
from typing import Any

TIMEOUT_SECONDS = 10
MAX_BYTES = 100 * 1024
MAX_URL = 500
TEXT_TYPES = ("text/", "application/json", "application/xml", "application/xhtml", "application/ld+json", "application/rss", "application/atom")
USER_AGENT = "socialnetwork-art-assistant/1"


class FetchError(ValueError):
    """The request is not allowed or failed; the message goes back to the model."""


@dataclass(frozen=True)
class Fetched:
    status: int
    content_type: str
    body: str
    truncated: bool


def allowed_hosts() -> set[str]:
    return {h.strip().lower().rstrip(".") for h in os.environ.get("HTTP_TOOL_ALLOWED_HOSTS", "").split(",") if h.strip()}


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip.is_private)


def check_url(url: str, hosts: set[str] | None = None) -> tuple[str, str, int, str]:
    """(scheme, host, port, path with query) of an allowed URL, or FetchError. `hosts` replaces the http_tool list."""
    if len(url) > MAX_URL:
        raise FetchError(f"The URL is longer than {MAX_URL} characters")
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    allow_http = os.environ.get("HTTP_TOOL_ALLOW_HTTP") == "1"
    if scheme != "https" and not (scheme == "http" and allow_http):
        raise FetchError("Only https URLs are allowed")
    if parts.username or parts.password:
        raise FetchError("A URL with a user name or password is not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise FetchError("The URL has no host")
    hosts = allowed_hosts() if hosts is None else hosts
    if not hosts:
        raise FetchError("This tool is not enabled on this server")
    if host not in hosts:
        raise FetchError(f"The host is not allowed. Allowed: {', '.join(sorted(hosts))}")
    port = parts.port or (443 if scheme == "https" else 80)
    if port not in (80, 443):
        raise FetchError("Only ports 80 and 443 are allowed")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return scheme, host, port, path


def resolve_public(host: str, port: int) -> str:
    """One public address of `host`; if any address is not public the host is refused outright."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise FetchError("The host could not be resolved") from None
    addresses = [info[4][0] for info in infos]
    if not addresses or not all(is_public(address) for address in addresses):
        raise FetchError("The host is not on the public internet")
    return addresses[0]


def fetch(url: str, method: str = "GET") -> Fetched:
    scheme, host, port, path = check_url(url)
    if method.upper() not in ("GET", "HEAD"):
        raise FetchError("Only GET and HEAD are allowed")
    return _send(scheme, host, port, path, method.upper(), {"Accept": "text/*, application/json"}, None)


def post_json(url: str, payload: bytes, hosts: set[str]) -> Fetched:
    """One POST of a JSON body to a URL on `hosts` (the MCP servers the operator named), under the same rules."""
    scheme, host, port, path = check_url(url, hosts)
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    return _send(scheme, host, port, path, "POST", headers, payload)


def _send(scheme: str, host: str, port: int, path: str, method: str, headers: dict[str, str], body: bytes | None) -> Fetched:
    address = resolve_public(host, port)
    try:
        sock = socket.create_connection((address, port), timeout=TIMEOUT_SECONDS)
        if scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        connection: http.client.HTTPConnection = (http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection)(host, port, timeout=TIMEOUT_SECONDS)
        connection.sock = sock  # the checked address, with the host name kept for the certificate and the Host header
        if body is None:
            connection.request(method, path, headers={"User-Agent": USER_AGENT, "Connection": "close", **headers})
        else:
            connection.request(method, path, body=body, headers={"User-Agent": USER_AGENT, "Connection": "close", **headers})
        response = connection.getresponse()
        content_type = (response.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if 300 <= response.status < 400:
            raise FetchError(f"The server redirected (HTTP {response.status}); redirects are not followed")
        if not content_type.startswith(TEXT_TYPES) and response.status != 204 and method != "HEAD":
            raise FetchError(f"Only text answers are returned, not {content_type or 'an unknown type'}")
        raw = b"" if method == "HEAD" else response.read(MAX_BYTES + 1)
        connection.close()
    except FetchError:
        raise
    except (OSError, http.client.HTTPException, ssl.SSLError) as error:
        raise FetchError(f"The request failed ({type(error).__name__})") from None
    truncated = len(raw) > MAX_BYTES
    return Fetched(response.status, content_type, raw[:MAX_BYTES].decode("utf-8", errors="replace"), truncated)


def describe() -> dict[str, Any]:
    return {"hosts": sorted(allowed_hosts())}
