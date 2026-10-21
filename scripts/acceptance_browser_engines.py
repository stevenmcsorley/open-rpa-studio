"""Local, network-free browser-engine and visible-scroll acceptance."""
from __future__ import annotations

import http.server
import socket
import threading
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from openrpa import browser_runtime
from openrpa.engine import WorkflowEngine


HTML = """<!doctype html><html><body>
<main><h1>Catalog page {page}</h1><article class='book'><h2>Book {page}</h2><span class='price'>£{price}</span><a href='/book/{page}'>Details</a></article>
<a rel='next' href='/?page={next}'>Next</a><div id='feed' style='height:220px;width:500px;overflow:auto'>{items}</div></main><div style='height:4800px'></div>
<script>window.scrollEvents=0;addEventListener('scroll',()=>window.scrollEvents++)</script>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        page = 2 if "page=2" in self.path else 1
        items = "".join(f"<article style='height:180px'>Feed item {index}</article>" for index in range(12))
        body = HTML.format(page=page, price="10.00" if page == 1 else "12.50", next=page + 1, items=items).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main() -> int:
    with closing(socket.socket()) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}/"
    status = browser_runtime.status()
    results: list[dict[str, object]] = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            for engine in ("chromium", "firefox", "webkit"):
                entry = status["engines"].get(engine, {})
                if not entry.get("available"):
                    results.append({"engine": engine, "status": "NOT_INSTALLED"})
                    continue
                browser = getattr(runtime, engine).launch(headless=True)
                try:
                    page = browser.new_page(viewport={"width": 1100, "height": 700})
                    events = []
                    page.on("console", lambda message: None)
                    page.goto(base, wait_until="domcontentloaded")
                    engine_core = WorkflowEngine.__new__(WorkflowEngine)
                    engine_core._browser = browser
                    engine_core._browser_context = page.context
                    engine_core._browser_page = page
                    engine_core._browser_tabs = {}
                    engine_core._check_cancel = lambda: None
                    engine_core._emit = lambda event, logs: (logs.append(event), events.append(event))
                    variables = {}
                    logs = []
                    engine_core._browser_activity({"id": "extract", "type": "browser_extract_records", "selectorKind": "css", "selector": "article.book", "fields": [
                        {"name": "title", "selector": "h2", "source": "text", "required": True},
                        {"name": "price", "selector": ".price", "source": "text", "required": True},
                        {"name": "url", "selector": "a", "source": "attribute:href", "required": True}], "maxRecords": 10, "maxOutputChars": 10000, "result": "books", "timeoutSeconds": 5}, variables, logs)
                    if len(variables["books"]) != 1 or variables["books"][0]["title"] != "Book 1":
                        raise AssertionError(f"{engine}: repeated-card extraction mismatch: {variables}")
                    page.locator("a[rel=next]").click()
                    if page.locator("h1").inner_text() != "Catalog page 2":
                        raise AssertionError(f"{engine}: visible next-page navigation failed")
                    engine_core._browser_page = page
                    engine_core._browser_activity({"id": "scroll", "type": "browser_scroll", "direction": "down", "distancePx": 900, "delayMilliseconds": 5, "toBottom": True, "maxSteps": 12, "result": "scrollResult"}, variables, logs)
                    if variables["scrollResult"]["scrollsCompleted"] < 2 or not variables["scrollResult"]["reachedBottom"]:
                        raise AssertionError(f"{engine}: gradual scroll did not reach document end: {variables['scrollResult']}")
                    if not events or events[-1]["event"] != "browser-scroll-progress":
                        raise AssertionError(f"{engine}: no live scroll progress events")
                    engine_core._browser_activity({"id": "scroll-feed", "type": "browser_scroll", "containerSelector": "#feed", "direction": "down", "distancePx": 180, "delayMilliseconds": 5, "toBottom": True, "maxSteps": 30, "result": "feedProgress"}, variables, logs)
                    feed_progress = variables["feedProgress"]
                    if feed_progress["target"] != "container" or feed_progress["scrollTop"] <= 0 or not feed_progress["reachedBottom"]:
                        raise AssertionError(f"{engine}: inner-feed scroll failed: {feed_progress}")
                    container_modes = sorted({str(event.get("inputMode")) for event in logs if event.get("activityId") == "scroll-feed"})
                    if not container_modes or not set(container_modes) <= {"wheel", "native-scroll-fallback"}:
                        raise AssertionError(f"{engine}: unexpected container scroll input modes: {container_modes}")
                    card_activity={"id":"collect-cards","type":"browser_extract_records","selectorKind":"css","selector":"article.item","fields":[{"name":"title","selector":"h2","source":"text","required":True},{"name":"url","selector":"a","source":"attribute","attribute":"href","required":True}],"append":True,"deduplicateBy":["url"],"maxRecords":20,"maxTotalRecords":20,"maxTotalOutputChars":10000,"result":"allBooks","timeoutSeconds":5}
                    page.set_content('<article class="item"><h2>Synth One</h2><a href="/item/1">one</a></article><article class="item"><h2>Synth Two</h2><a href="/item/2">two</a></article>')
                    engine_core._browser_page=page
                    engine_core._browser_activity(card_activity,variables,logs)
                    page.set_content('<article class="item"><h2>Synth Two duplicate</h2><a href="/item/2">two</a></article><article class="item"><h2>Synth Three</h2><a href="/item/3">three</a></article>')
                    engine_core._browser_activity(card_activity,variables,logs)
                    if len(variables["allBooks"])!=3 or logs[-1].get("duplicatesSkipped")!=1:
                        raise AssertionError(f"{engine}: overlapping card extraction did not deduplicate by URL: {variables['allBooks']}")
                    results.append({"engine": engine, "status": "PASS", "browserVersion": browser.version,
                                    "extractedRecords": len(variables["books"]), "pagination": "PASS",
                                    "scrollSteps": variables["scrollResult"]["scrollsCompleted"],
                                    "containerScrollSteps": feed_progress["scrollsCompleted"],
                                    "containerInputModes": container_modes,
                                    "deduplicatedRecords":len(variables["allBooks"]),"duplicateCardsSkipped":logs[-1]["duplicatesSkipped"],
                                    "progressEvents": len(events), "reachedBottom": variables["scrollResult"]["reachedBottom"]})
                finally:
                    browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    for item in results:
        print(item)
    return 1 if any(item.get("status") == "FAIL" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
