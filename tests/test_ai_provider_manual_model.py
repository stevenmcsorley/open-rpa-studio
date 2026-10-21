import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from openrpa import ai_providers as ai


class _CompatibleModelHost(BaseHTTPRequestHandler):
    requests=[]

    def log_message(self,*_args):
        pass

    def do_GET(self):
        type(self).requests.append(("GET",self.path,None))
        self.send_error(404,"model catalogue disabled")

    def do_POST(self):
        length=int(self.headers.get("Content-Length","0"))
        body=json.loads(self.rfile.read(length))
        type(self).requests.append(("POST",self.path,body))
        payload=json.dumps({"choices":[{"message":{"content":json.dumps({"explanation":"Drafted with the manually selected model.","activities":[{"id":"log-1","type":"log","message":"hello"}]})}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_compatible_endpoint_can_draft_when_catalog_is_unavailable():
    _CompatibleModelHost.requests=[]
    server=ThreadingHTTPServer(("127.0.0.1",0),_CompatibleModelHost)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        base=f"http://127.0.0.1:{server.server_port}/v1"
        with pytest.raises(ValueError,match="HTTP 404"):
            ai.models("local_openai_compatible",base)

        result=ai.draft("local_openai_compatible","tenant-model-2026","log hello",["log"],base)

        assert result["activities"][0]["type"]=="log"
        assert _CompatibleModelHost.requests[0][:2]==("GET","/v1/models")
        method,path,request=_CompatibleModelHost.requests[1]
        assert (method,path)==("POST","/v1/chat/completions")
        assert request["model"]=="tenant-model-2026"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
