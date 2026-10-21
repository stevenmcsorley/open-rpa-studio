"""Verify installed AI model discovery against a credential-free local endpoint."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class ModelsHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != "/v1/models":
            self.send_error(404)
            return
        body = json.dumps({"data": [{"id": "local-test-a"}, {"id": "local-test-b"}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: installed_ai_models_acceptance.py BRIDGE_EXE DATA_DIRECTORY")
    executable = Path(sys.argv[1]).resolve()
    data_dir = Path(sys.argv[2]).resolve()
    if data_dir.exists() and any(data_dir.iterdir()):
        raise SystemExit(f"Refusing non-empty acceptance directory: {data_dir}")
    data_dir.mkdir(parents=True, exist_ok=True)
    server = HTTPServer(("127.0.0.1", 0), ModelsHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        request = {"id": 1, "method": "ai.models", "params": {
            "provider": "local_openai_compatible",
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
        }}
        result = subprocess.run([str(executable)], input=json.dumps(request) + "\n", capture_output=True,
                                text=True, encoding="utf-8",
                                env={**os.environ, "OPENRPA_DATA_DIR": str(data_dir)}, timeout=30)
        replies = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        if result.returncode or not replies or "error" in replies[0]:
            raise AssertionError({"exit": result.returncode, "stderr": result.stderr, "responses": replies})
        assert replies[0]["result"]["models"] == ["local-test-a", "local-test-b"]
        assert replies[0]["result"]["provider"] == "local_openai_compatible"
        print("PASS: installed AI bridge verified the local endpoint and returned its two model IDs without credentials")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
