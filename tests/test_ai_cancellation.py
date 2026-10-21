import json
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openrpa import ai_providers


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
