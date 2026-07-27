import json
import os
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Optional

from ..core.utils import (
    SHARED_SESSION, apply_browser_headers, build_proxy_url,
    app_dir,
)
from ..core.proxy_manager import ProxyManager
from ..core.records import RecordsManager
from ..core.logger import AccessLogger


class ProxyHandler(BaseHTTPRequestHandler):
    proxy_manager: Optional[ProxyManager] = None
    records_manager: Optional[RecordsManager] = None

    def log_message(self, format, *args):
        pass

    def _get_target_url(self) -> str:
        target = self.path.lstrip("/")
        if not target:
            return ""
        if target.startswith("https:/") and not target.startswith("https://"):
            target = "https://" + target[len("https:/"):]
        elif target.startswith("http:/") and not target.startswith("http://"):
            target = "http://" + target[len("http:/"):]
        if not target.startswith("http://") and not target.startswith("https://"):
            target = "https://" + target
        return target

    def do_GET(self):
        if self.path == "/health":
            self._health()
            return
        if self.path == "/api/status":
            self._status()
            return
        self._proxy()

    def do_HEAD(self):
        if self.path == "/health":
            self._health()
            return
        if self.path == "/api/status":
            self._status()
            return
        self._proxy()

    def _health(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def _status(self):
        proxies = self.proxy_manager.get_all() if self.proxy_manager else []
        available = sum(1 for p in proxies if p.status == "active" and p.enabled)
        body = json.dumps({
            "running": True,
            "availableProxies": available,
            "totalProxies": len(proxies),
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def _proxy(self):
        target_url = self._get_target_url()
        if not target_url:
            self.send_error(400, "Usage: http://127.0.0.1:9090/<url-to-download>")
            return

        log = AccessLogger.get()
        if log:
            log.log("REQUEST %s from %s", target_url, self.client_address[0])

        proxies = self.proxy_manager.get_all() if self.proxy_manager else []
        last_err = None
        for p in proxies:
            if p.status != "active" or not p.enabled or not p.scheme:
                continue
            proxy_url = build_proxy_url(p.scheme, p.domain, target_url)
            if log:
                log.log("TRY %s", p.domain)

            start = time.time()
            try:
                bytes_written = self._proxy_request(proxy_url)
                elapsed = time.time() - start
                if bytes_written > 0 and elapsed > 0:
                    speed_mbps = (bytes_written / elapsed) * 8 / 1_000_000
                    if log:
                        log.log("SUCCESS %s - %d bytes, %.1f Mbps", p.domain, bytes_written, speed_mbps)
                    if self.records_manager:
                        self.records_manager.record_success(p.domain, bytes_written, speed_mbps)
                    return
            except Exception as e:
                if log:
                    log.log("FAIL %s: %v", p.domain, e)
                last_err = e

        if log:
            log.log("ALL FAILED: %v", last_err)
        self.send_error(502, f"all proxies failed: {last_err}")

    def _proxy_request(self, proxy_url: str) -> int:
        headers = dict(self.headers)
        apply_browser_headers(headers)

        try:
            resp = SHARED_SESSION.get(
                proxy_url,
                headers=headers,
                stream=True,
                timeout=None,
            )
        except Exception as e:
            raise Exception(f"proxy request failed: {e}")

        if resp.status_code >= 400:
            resp.close()
            raise Exception(f"proxy returned {resp.status_code}")

        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct.lower():
            resp.close()
            raise Exception("proxy returned text/html (landing page)")

        self.send_response(resp.status_code)
        for key, value in resp.headers.items():
            if key.lower() not in ("transfer-encoding", "content-encoding"):
                self.send_header(key, value)
        self.send_header("X-Proxy", proxy_url)
        self.end_headers()

        written = 0
        try:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    self.wfile.write(chunk)
                    written += len(chunk)
        except Exception:
            pass
        resp.close()
        return written


class ProxyServer:
    def __init__(self, proxy_manager: ProxyManager, records_manager: RecordsManager):
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._port = 9090
        self._host = "127.0.0.1"
        self._proxy_manager = proxy_manager
        self._records_manager = records_manager

    @property
    def address(self) -> str:
        return f"http://{self._host}:{self._port}"

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, port: int, allow_remote: bool = False):
        if self._running:
            return
        self._port = port
        self._host = "0.0.0.0" if allow_remote else "127.0.0.1"

        ProxyHandler.proxy_manager = self._proxy_manager
        ProxyHandler.records_manager = self._records_manager

        self._server = ThreadingHTTPServer((self._host, self._port), ProxyHandler)
        self._server.timeout = 0.5
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self):
        if not self._running or not self._server:
            return
        self._server.shutdown()
        self._thread = None
        self._server = None
        self._running = False
