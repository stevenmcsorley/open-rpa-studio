"""Restricted public HTTPS/HTTP client for workflow HTTP activities.

DNS is resolved once, every answer must be globally routable, and the socket is
pinned to one validated address. Redirects are deliberately returned to the
workflow instead of being followed implicitly.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit


class EgressDenied(ValueError):
    pass


def _target(url: str) -> tuple[str, int, str, str]:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise EgressDenied("Only absolute HTTP or HTTPS URLs are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise EgressDenied("Credentials embedded in URLs are not allowed")
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
            raise EgressDenied("Local and internal hostnames are blocked")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            raise EgressDenied("Only the standard HTTP (80) and HTTPS (443) ports are allowed")
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        return parsed.scheme, port, host, target
    except ValueError as exc:
        if isinstance(exc, EgressDenied):
            raise
        raise EgressDenied("Invalid URL or port") from exc


def _resolve_public(host: str, port: int) -> str:
    try:
        literal = ipaddress.ip_address(host)
        addresses = [str(literal)]
    except ValueError:
        try:
            answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise EgressDenied(f"DNS lookup failed for {host}: {exc}") from exc
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses:
        raise EgressDenied(f"DNS returned no addresses for {host}")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise EgressDenied("DNS returned an invalid address") from exc
        if not ip.is_global:
            raise EgressDenied(f"Host {host} resolves to a non-public address")
    return addresses[0]


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self.address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self) -> None:
        raw = socket.create_connection((self.address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def request(url: str, method: str, headers: dict[str, str], body: bytes | None,
            timeout: float, max_bytes: int) -> dict[str, object]:
    scheme, port, host, target = _target(url)
    timeout = min(max(float(timeout), 1.0), 60.0)
    max_bytes = min(max(int(max_bytes), 1), 5_000_000)
    address = _resolve_public(host, port)
    connection_class = _PinnedHTTPS if scheme == "https" else _PinnedHTTP
    connection = connection_class(host, port, address, timeout)
    try:
        connection.request(method.upper(), target, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise EgressDenied("HTTP response exceeded configured size limit")
        return {"status": response.status, "headers": dict(response.getheaders()),
                "body": payload.decode("utf-8", errors="replace"),
                "redirectBlocked": 300 <= response.status < 400}
    finally:
        connection.close()


def assert_public_url(url: str) -> None:
    """Validate a browser URL and its current DNS answers before navigation.

    Browser networking cannot pin DNS sockets like the HTTP activity can, so
    this is a redirect-aware blocklist check with a residual DNS race.
    """
    scheme,port,host,_target_path=_target(url)
    _resolve_public(host,port)

