"""Restricted public HTTPS/HTTP client for workflow HTTP activities.

DNS is resolved once, every answer must be globally routable, and the socket is
pinned to one validated address. Redirects are deliberately returned to the
workflow instead of being followed implicitly.
"""
from __future__ import annotations

import http.client
import errno
import ipaddress
import select
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit


class EgressDenied(ValueError):
    pass


class RequestCancelled(Exception):
    """Raised when a caller cancels an in-flight HTTP request."""


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise RequestCancelled("Provider request was cancelled")


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
            timeout: float, max_bytes: int,
            cancel: threading.Event | None = None) -> dict[str, object]:
    if cancel is not None:
        scheme, port, host, target = _target(url)
        address = _resolve_public(host, port)
        return _request_cancellable(scheme, host, port, address, target, method,
                                    headers, body, timeout, max_bytes, cancel)
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


def request_loopback(url: str, method: str, headers: dict[str, str], body: bytes | None,
                     timeout: float, max_bytes: int,
                     cancel: threading.Event | None = None) -> dict[str, object]:
    """Cancellable HTTP client for explicitly configured loopback model servers."""
    _check_cancel(cancel)
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "http" or host not in {"127.0.0.1", "::1", "localhost"}
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise EgressDenied("Local model requests must use plain HTTP on a loopback host")
        port = parsed.port or 80
    except ValueError as exc:
        raise EgressDenied("Invalid local model URL") from exc
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    timeout = min(max(float(timeout), 1.0), 180.0)
    max_bytes = min(max(int(max_bytes), 1), 5_000_000)
    _check_cancel(cancel)
    if cancel is not None:
        return _request_cancellable("http", host, port, host, target, method,
                                    headers, body, timeout, max_bytes, cancel)
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
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


def _wait_socket(sock: socket.socket, *, read: bool, write: bool,
                 cancel: threading.Event, deadline: float) -> None:
    while True:
        _check_cancel(cancel)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Provider request timed out")
        readable, writable, exceptional = select.select(
            [sock] if read else [], [sock] if write else [], [sock], min(remaining, 0.1))
        if exceptional:
            raise OSError("Provider socket reported an exceptional condition")
        if (read and readable) or (write and writable):
            return


def _connect_cancellable(host: str, port: int, address: str, cancel: threading.Event,
                         deadline: float) -> socket.socket:
    infos = socket.getaddrinfo(address, port, type=socket.SOCK_STREAM)
    last_error: OSError | None = None
    for family, socktype, proto, _canonname, sockaddr in infos:
        _check_cancel(cancel)
        sock = socket.socket(family, socktype, proto)
        sock.setblocking(False)
        try:
            result = sock.connect_ex(sockaddr)
            if result not in (0, errno.EISCONN):
                pending_errors = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY,
                                  getattr(errno, "WSAEWOULDBLOCK", 10035),
                                  getattr(errno, "WSAEINPROGRESS", 10036)}
                if result not in pending_errors:
                    raise OSError(result, "Could not connect to provider")
                _wait_socket(sock, read=False, write=True, cancel=cancel, deadline=deadline)
                error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if error:
                    raise OSError(error, "Could not connect to provider")
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
            if time.monotonic() >= deadline:
                break
    if last_error is not None:
        raise last_error
    raise OSError("Provider DNS returned no usable socket addresses")


def _send_cancellable(sock: socket.socket, data: bytes, cancel: threading.Event,
                      deadline: float) -> None:
    view = memoryview(data)
    while view:
        _check_cancel(cancel)
        try:
            sent = sock.send(view)
            if sent == 0:
                raise OSError("Provider socket closed while sending the request")
            view = view[sent:]
        except (BlockingIOError, ssl.SSLWantWriteError):
            _wait_socket(sock, read=False, write=True, cancel=cancel, deadline=deadline)
        except ssl.SSLWantReadError:
            _wait_socket(sock, read=True, write=False, cancel=cancel, deadline=deadline)
        if not view:
            return


def _receive_cancellable(sock: socket.socket, cancel: threading.Event,
                         deadline: float, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    limit = max_bytes + 65536
    while True:
        _wait_socket(sock, read=True, write=False, cancel=cancel, deadline=deadline)
        try:
            chunk = sock.recv(min(65536, limit + 1 - size))
        except (BlockingIOError, ssl.SSLWantReadError):
            continue
        except ssl.SSLWantWriteError:
            _wait_socket(sock, read=False, write=True, cancel=cancel, deadline=deadline)
            continue
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            raise EgressDenied("Provider response exceeded the configured size limit")


def _decode_response(raw: bytes, max_bytes: int) -> dict[str, object]:
    marker = raw.find(b"\r\n\r\n")
    if marker < 0 or marker > 65536:
        raise EgressDenied("Provider returned an invalid or oversized HTTP header")
    head = raw[:marker].decode("iso-8859-1", errors="replace").split("\r\n")
    try:
        status_parts = head[0].split(" ", 2)
        version, status_text = status_parts[:2]
        if not version.startswith("HTTP/"):
            raise ValueError
        status = int(status_text)
    except (ValueError, IndexError):
        raise EgressDenied("Provider returned an invalid HTTP status line") from None
    response_headers: dict[str, str] = {}
    for line in head[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = name.strip().lower()
        response_headers[key] = f"{response_headers[key]}, {value.strip()}" if key in response_headers else value.strip()
    payload = raw[marker + 4:]
    if "chunked" in response_headers.get("transfer-encoding", "").lower():
        decoded = bytearray()
        offset = 0
        while True:
            end = payload.find(b"\r\n", offset)
            if end < 0:
                raise EgressDenied("Provider returned a truncated chunked response")
            try:
                length = int(payload[offset:end].split(b";", 1)[0], 16)
            except ValueError:
                raise EgressDenied("Provider returned an invalid chunked response") from None
            offset = end + 2
            if length == 0:
                break
            if length < 0 or len(decoded) + length > max_bytes:
                raise EgressDenied("Provider response exceeded the configured size limit")
            if len(payload) < offset + length + 2 or payload[offset + length:offset + length + 2] != b"\r\n":
                raise EgressDenied("Provider returned a truncated chunked response")
            decoded.extend(payload[offset:offset + length])
            offset += length + 2
        payload = bytes(decoded)
    elif "content-length" in response_headers:
        try:
            expected = int(response_headers["content-length"])
        except ValueError:
            raise EgressDenied("Provider returned an invalid Content-Length") from None
        if expected < 0 or expected > max_bytes:
            raise EgressDenied("Provider response exceeded the configured size limit")
        if len(payload) < expected:
            raise EgressDenied("Provider response ended before Content-Length bytes arrived")
        payload = payload[:expected]
    if len(payload) > max_bytes:
        raise EgressDenied("Provider response exceeded the configured size limit")
    return {"status": status, "headers": response_headers,
            "body": payload.decode("utf-8", errors="replace"),
            "redirectBlocked": 300 <= status < 400}


class _SocketReader:
    """Bounded, cancellable response reader for incremental HTTP/SSE bodies."""
    def __init__(self,sock:socket.socket,cancel:threading.Event,deadline:float,max_bytes:int,on_chunk):
        self.sock=sock;self.cancel=cancel;self.deadline=deadline;self.max_bytes=max_bytes
        self.on_chunk=on_chunk;self.buffer=bytearray();self.total=0;self.body=bytearray()

    def _more(self)->bool:
        while True:
            _wait_socket(self.sock,read=True,write=False,cancel=self.cancel,deadline=self.deadline)
            try:chunk=self.sock.recv(65536)
            except (BlockingIOError,ssl.SSLWantReadError):continue
            except ssl.SSLWantWriteError:
                _wait_socket(self.sock,read=False,write=True,cancel=self.cancel,deadline=self.deadline);continue
            if not chunk:return False
            self.buffer.extend(chunk);return True

    def line(self,limit:int=65536)->bytes:
        while True:
            index=self.buffer.find(b"\r\n")
            if index>=0:
                line=bytes(self.buffer[:index]);del self.buffer[:index+2];return line
            if len(self.buffer)>limit:raise EgressDenied("Provider returned an oversized HTTP line")
            if not self._more():raise EgressDenied("Provider returned a truncated HTTP response")

    def exact(self,count:int)->bytes:
        if count<0 or count>self.max_bytes+65536:raise EgressDenied("Provider response exceeded the configured size limit")
        while len(self.buffer)<count:
            if not self._more():raise EgressDenied("Provider returned a truncated HTTP response")
        value=bytes(self.buffer[:count]);del self.buffer[:count];return value

    def emit(self,value:bytes)->None:
        if not value:return
        self.total+=len(value)
        if self.total>self.max_bytes:raise EgressDenied("Provider response exceeded the configured size limit")
        self.body.extend(value);self.on_chunk(value)

    def to_close(self)->None:
        while True:
            if self.buffer:self.emit(bytes(self.buffer));self.buffer.clear()
            _wait_socket(self.sock,read=True,write=False,cancel=self.cancel,deadline=self.deadline)
            try:chunk=self.sock.recv(65536)
            except (BlockingIOError,ssl.SSLWantReadError):continue
            except ssl.SSLWantWriteError:
                _wait_socket(self.sock,read=False,write=True,cancel=self.cancel,deadline=self.deadline);continue
            if not chunk:return
            self.emit(chunk)


def _decode_stream_response(sock:socket.socket,cancel:threading.Event,deadline:float,max_bytes:int,on_chunk,on_headers=None):
    reader=_SocketReader(sock,cancel,deadline,max_bytes,on_chunk)
    status_line=reader.line().decode("iso-8859-1",errors="replace")
    try:
        version,status_text,*_=status_line.split(" ",2);status=int(status_text)
        if not version.startswith("HTTP/"):raise ValueError
    except (ValueError,IndexError):raise EgressDenied("Provider returned an invalid HTTP status line") from None
    response_headers={}
    header_bytes=0
    while True:
        line=reader.line();header_bytes+=len(line)+2
        if header_bytes>65536:raise EgressDenied("Provider returned oversized HTTP headers")
        if not line:break
        if b":" not in line:continue
        name,value=line.split(b":",1);key=name.decode("ascii","ignore").strip().lower()
        if key:response_headers[key]=value.decode("iso-8859-1").strip()
    if on_headers:on_headers(status,response_headers)
    transfer=response_headers.get("transfer-encoding","").lower()
    if "chunked" in transfer:
        while True:
            size_line=reader.line(8192).split(b";",1)[0].strip()
            try:size=int(size_line,16)
            except ValueError:raise EgressDenied("Provider returned an invalid chunked response") from None
            if size==0:
                while reader.line():pass
                break
            if reader.total+size>max_bytes:raise EgressDenied("Provider response exceeded the configured size limit")
            reader.emit(reader.exact(size))
            if reader.exact(2)!=b"\r\n":raise EgressDenied("Provider returned a malformed chunked response")
    elif "content-length" in response_headers:
        try:length=int(response_headers["content-length"])
        except ValueError:raise EgressDenied("Provider returned invalid Content-Length") from None
        if length<0 or length>max_bytes:raise EgressDenied("Provider response exceeded the configured size limit")
        remaining=length
        while remaining:
            chunk=reader.exact(min(65536,remaining));reader.emit(chunk);remaining-=len(chunk)
    else:reader.to_close()
    return {"status":status,"headers":response_headers,"body":bytes(reader.body).decode("utf-8",errors="replace"),
        "redirectBlocked":300<=status<400}


def _request_cancellable(scheme: str, host: str, port: int, address: str, target: str,
                         method: str, headers: dict[str, str], body: bytes | None,
                         timeout: float, max_bytes: int,
                         cancel: threading.Event,on_chunk=None,on_headers=None) -> dict[str, object]:
    timeout = min(max(float(timeout), 1.0), 180.0)
    max_bytes = min(max(int(max_bytes), 1), 8_000_000)
    if not method or any(character in method for character in " \r\n\t"):
        raise EgressDenied("Invalid provider HTTP method")
    if any(character in target for character in "\r\n\t") or " " in target:
        raise EgressDenied("Invalid provider request target")
    request_headers = {key.lower(): value for key, value in headers.items()}
    if any(not key or any(character in key for character in ":\r\n\t ")
           or any(character in value for character in "\r\n")
           for key, value in request_headers.items()):
        raise EgressDenied("Invalid provider HTTP header")
    deadline = time.monotonic() + timeout
    sock = _connect_cancellable(host, port, address, cancel, deadline)
    try:
        if scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host, do_handshake_on_connect=False)
            sock.setblocking(False)
            while True:
                _check_cancel(cancel)
                try:
                    sock.do_handshake()
                    break
                except ssl.SSLWantReadError:
                    _wait_socket(sock, read=True, write=False, cancel=cancel, deadline=deadline)
                except ssl.SSLWantWriteError:
                    _wait_socket(sock, read=False, write=True, cancel=cancel, deadline=deadline)
        formatted_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        request_headers.setdefault("host", f"{formatted_host}:{port}" if port not in {80, 443} else formatted_host)
        request_headers.setdefault("connection", "close")
        request_headers.setdefault("accept-encoding", "identity")
        payload = body or b""
        if body is not None:
            request_headers.setdefault("content-length", str(len(payload)))
        head = [f"{method.upper()} {target} HTTP/1.1"]
        head.extend(f"{key}: {value}" for key, value in request_headers.items())
        _send_cancellable(sock, ("\r\n".join(head) + "\r\n\r\n").encode("iso-8859-1") + payload, cancel, deadline)
        if on_chunk is not None:return _decode_stream_response(sock,cancel,deadline,max_bytes,on_chunk,on_headers)
        raw = _receive_cancellable(sock, cancel, deadline, max_bytes)
        return _decode_response(raw, max_bytes)
    except RequestCancelled:
        raise
    except Exception:
        if cancel.is_set():
            raise RequestCancelled("Provider request was cancelled") from None
        raise
    finally:
        try:
            sock.close()
        except OSError:
            pass


def request_stream(url:str,method:str,headers:dict[str,str],body:bytes|None,timeout:float,max_bytes:int,
                  on_chunk,cancel:threading.Event|None=None,on_headers=None)->dict[str,object]:
    """Make a public pinned request and deliver decoded response chunks as received."""
    scheme,port,host,target=_target(url);address=_resolve_public(host,port)
    cancellation=cancel or threading.Event()
    return _request_cancellable(scheme,host,port,address,target,method,headers,body,timeout,max_bytes,cancellation,on_chunk,on_headers)


def request_loopback_stream(url:str,method:str,headers:dict[str,str],body:bytes|None,timeout:float,max_bytes:int,
                            on_chunk,cancel:threading.Event|None=None,on_headers=None)->dict[str,object]:
    """Stream only from an explicitly configured loopback model endpoint."""
    try:
        parsed=urlsplit(url);host=(parsed.hostname or "").lower()
        if (parsed.scheme!="http" or host not in {"127.0.0.1","::1","localhost"}
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment):
            raise EgressDenied("Local model requests must use plain HTTP on a loopback host")
        port=parsed.port or 80;target=parsed.path or "/"
    except ValueError as exc:raise EgressDenied("Invalid local model URL") from exc
    cancellation=cancel or threading.Event()
    return _request_cancellable("http",host,port,host,target,method,headers,body,timeout,max_bytes,cancellation,on_chunk,on_headers)


def assert_public_url(url: str) -> None:
    """Validate a browser URL and its current DNS answers before navigation.

    Browser networking cannot pin DNS sockets like the HTTP activity can, so
    this is a redirect-aware blocklist check with a residual DNS race.
    """
    scheme,port,host,_target_path=_target(url)
    _resolve_public(host,port)

