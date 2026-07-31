import json
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional

from .utils import get_viper, apply_browser_headers

PROXY_PORT = 6801


class _ViperProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self._forward("GET")

    def do_HEAD(self):
        self._forward("HEAD")

    def _forward(self, method):
        target = self.path.lstrip("/")
        if not target.startswith("http://") and not target.startswith("https://"):
            self.send_error(400, b"Usage: /<url>")
            return
        headers = {"Accept-Encoding": "identity"}
        apply_browser_headers(headers)
        for h in ("Range", "If-Modified-Since", "If-None-Match"):
            v = self.headers.get(h)
            if v:
                headers[h] = v
        viper = get_viper()
        if viper is None:
            self.send_error(502, "vipertls not available")
            return
        try:
            if method == "HEAD":
                resp = viper.head(target, headers=headers)
                self.send_response(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "connection", "keep-alive", "content-encoding"):
                        self.send_header(k, v)
                self.end_headers()
                return
            resp = viper.get(target, headers=headers, stream=True)
        except Exception as e:
            self.send_error(502, str(e)[:200])
            return
        body = resp.content
        self.send_response(resp.status_code)
        skip = {"transfer-encoding", "connection", "keep-alive", "content-encoding", "content-length"}
        for k, v in resp.headers.items():
            if k.lower() not in skip:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)
            self.wfile.flush()


class ViperProxy:
    def __init__(self, port: int = PROXY_PORT):
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._port = port

    @property
    def proxy_url(self):
        return f"http://127.0.0.1:{self._port}"

    def start(self):
        if self._server:
            return
        self._server = ThreadingHTTPServer(("127.0.0.1", self._port), _ViperProxyHandler)
        self._server.timeout = 0.5
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
