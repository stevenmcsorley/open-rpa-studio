import json
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openrpa import ai_providers
from openrpa.network import request_loopback_stream


class _SlowLocalModel(BaseHTTPRequestHandler):
    received = threading.Event()
    release = threading.Event()

    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).received.set()
        type(self).release.wait(10)
        payload = json.dumps({"choices": [{"message": {"content": '{"explanation":"ok","activities":[]}'}}]}).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class _ImmediateLocalModel(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        draft = {"explanation": "local test response", "activities": [{"id": "log-1", "type": "log", "message": "ok"}]}
        payload = json.dumps({"choices": [{"message": {"content": json.dumps(draft)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _ChunkedStream(BaseHTTPRequestHandler):
    def log_message(self,*_args):pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length","0")))
        self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Transfer-Encoding","chunked");self.end_headers()
        for piece in (b"data: first",b"-event\r\n\r\ndata: second\n\n"):
            self.wfile.write(f"{len(piece):x}\r\n".encode()+piece+b"\r\n");self.wfile.flush();time.sleep(.02)
        self.wfile.write(b"0\r\n\r\n");self.wfile.flush()


class _LargeChunkedStream(BaseHTTPRequestHandler):
    payload=b"x"*6_000_000
    def log_message(self,*_args):pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length","0")))
        self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Transfer-Encoding","chunked");self.end_headers()
        for offset in range(0,len(type(self).payload),65536):
            piece=type(self).payload[offset:offset+65536]
            self.wfile.write(f"{len(piece):x}\r\n".encode()+piece+b"\r\n")
        self.wfile.write(b"0\r\n\r\n");self.wfile.flush()


class _SlowChunkedStream(BaseHTTPRequestHandler):
    sent=threading.Event();release=threading.Event()
    def log_message(self,*_args):pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length","0")))
        self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Transfer-Encoding","chunked");self.end_headers()
        chunk=b"data: first\n\n";self.wfile.write(f"{len(chunk):x}\r\n".encode()+chunk+b"\r\n");self.wfile.flush();type(self).sent.set()
        type(self).release.wait(5)
        try:self.wfile.write(b"0\r\n\r\n");self.wfile.flush()
        except OSError:pass


def test_native_cancellable_transport_returns_a_valid_model_response():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ImmediateLocalModel)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        draft = ai_providers.draft(
            "local_openai_compatible", "test-model", "make a log", ["log"],
            f"http://127.0.0.1:{server.server_port}/v1", cancel=threading.Event())
        assert draft["activities"][0]["message"] == "ok"
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


def test_loopback_stream_transport_delivers_decoded_http_chunks_incrementally():
    server=ThreadingHTTPServer(("127.0.0.1",0),_ChunkedStream)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();received=[]
    try:
        result=request_loopback_stream(f"http://127.0.0.1:{server.server_port}/v1/chat/completions","POST",
            {"Content-Type":"application/json"},b"{}",5,100000,received.append,threading.Event())
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    assert result["status"]==200
    assert b"".join(received)==b"data: first-event\r\n\r\ndata: second\n\n"


def test_loopback_stream_accepts_large_bounded_reasoning_payload():
    server=ThreadingHTTPServer(("127.0.0.1",0),_LargeChunkedStream)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();received=[]
    try:
        result=request_loopback_stream(f"http://127.0.0.1:{server.server_port}/v1/chat/completions","POST",{},b"{}",10,
            ai_providers.MAX_STREAM_RESPONSE_BYTES,received.append,threading.Event())
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    assert result["status"]==200
    assert sum(map(len,received))==6_000_000


def test_loopback_stream_cancellation_closes_waiting_provider_socket():
    _SlowChunkedStream.sent=threading.Event();_SlowChunkedStream.release=threading.Event()
    server=ThreadingHTTPServer(("127.0.0.1",0),_SlowChunkedStream)
    server_thread=threading.Thread(target=server.serve_forever,daemon=True);server_thread.start()
    cancellation=threading.Event();errors=[]
    def request():
        try:request_loopback_stream(f"http://127.0.0.1:{server.server_port}/v1/chat/completions","POST",{},b"{}",5,100000,lambda _chunk:None,cancellation)
        except BaseException as exc:errors.append(exc)
    client=threading.Thread(target=request,daemon=True);client.start()
    try:
        assert _SlowChunkedStream.sent.wait(2)
        cancellation.set();client.join(2)
        assert not client.is_alive()
        assert len(errors)==1 and isinstance(errors[0],ai_providers.RequestCancelled)
    finally:
        _SlowChunkedStream.release.set();server.shutdown();server.server_close();server_thread.join(timeout=2)


def test_native_bridge_cancels_local_model_transport(tmp_path):
    _SlowLocalModel.received = threading.Event()
    _SlowLocalModel.release = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowLocalModel)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    environment = os.environ.copy()
    environment["OPENRPA_DATA_DIR"] = str(tmp_path)
    environment["PYTHONNOUSERSITE"] = "1"
    bridge = subprocess.Popen(
        [sys.executable, "-m", "openrpa.bridge"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
    )
    responses = queue.Queue()
    raw_responses = queue.Queue()
    diagnostics = queue.Queue()

    def read_responses():
        assert bridge.stdout is not None
        for line in bridge.stdout:
            raw_responses.put(line)
            try:
                responses.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    reader = threading.Thread(target=read_responses, daemon=True)
    reader.start()
    def read_diagnostics():
        assert bridge.stderr is not None
        for line in bridge.stderr:
            diagnostics.put(line)
    stderr_reader = threading.Thread(target=read_diagnostics, daemon=True)
    stderr_reader.start()
    try:
        assert bridge.stdin is not None
        request = {
            "id": 1,
            "method": "ai.draft",
            "params": {
                "draftId": "cancel-test-1",
                "provider": "local_openai_compatible",
                "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
                "model": "test-model",
                "prompt": "Create a harmless draft",
                "workflows": ["Main"],
                "executionModel": "sequence",
            },
        }
        bridge.stdin.write(json.dumps(request) + "\n")
        bridge.stdin.flush()
        assert _SlowLocalModel.received.wait(5), "Model request never reached the local test server"

        started = time.monotonic()
        bridge.stdin.write(json.dumps({"id": 2, "method": "ai.cancel", "params": {"draftId": "cancel-test-1"}}) + "\n")
        bridge.stdin.flush()
        frames = {}
        while 2 not in frames or 1 not in frames:
            try:
                frame = responses.get(timeout=3)
            except queue.Empty as exc:
                details=[]
                while not diagnostics.empty(): details.append(diagnostics.get_nowait())
                raw=[]
                while not raw_responses.empty(): raw.append(raw_responses.get_nowait())
                raise AssertionError(f"Timed out waiting for bridge replies; child poll={bridge.poll()}; stdout={raw}; stderr={''.join(details)}") from exc
            if "id" in frame:
                frames[frame["id"]] = frame
        assert time.monotonic() - started < 2, "Cancellation waited for the slow provider response"
        assert frames[2]["result"]["cancelled"] is True
        assert "cancelled" in frames[1]["error"]["message"].lower()
    finally:
        _SlowLocalModel.release.set()
        if bridge.poll() is None:
            bridge.terminate()
            bridge.wait(timeout=5)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
