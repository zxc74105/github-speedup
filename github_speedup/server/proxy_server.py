import json
import os
import shutil
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Optional

import requests

from ..core.utils import (
    SHARED_SESSION, apply_browser_headers, find_active_proxies_file,
    app_dir,
)
from ..core.downloader import get_file_size_via_proxies, guess_file_name
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
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()

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

    def _read_proxy_list(self) -> list:
        result = []
        try:
            with open(find_active_proxies_file(), "r", encoding="utf-8") as f:
                entries = json.load(f)
            for e in entries:
                if e.get("status") == "active" and e.get("enabled", True):
                    s = e.get("scheme", "https")
                    d = e.get("domain", "")
                    if s and d:
                        result.append(f"{s}://{d}")
        except Exception:
            pass
        return result

    def _proxy(self):
        target_url = self._get_target_url()
        if not target_url:
            self.send_error(400, "Usage: http://127.0.0.1:9090/<url-to-download>")
            return

        log = AccessLogger.get()
        if log:
            log.log("API STREAM %s from %s", target_url, self.client_address[0])

        proxy_list = self._read_proxy_list()
        if not proxy_list:
            self.send_error(502, "no active proxies available")
            return

        file_size = get_file_size_via_proxies(proxy_list, target_url, 30)
        if file_size <= 0:
            self.send_error(502, "cannot determine file size")
            return

        file_name = guess_file_name(target_url)
        temp_dir = tempfile.mkdtemp(prefix="gs_")
        output_path = os.path.join(temp_dir, file_name)

        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
            self.send_header("Content-Length", str(file_size))
            self.send_header("X-Download-Mode", "stream")
            self.end_headers()

            total_written = 0
            for attempt, px in enumerate(proxy_list):
                dl_url = f"{px}/{target_url}"
                headers = {"Accept-Encoding": "identity"}
                apply_browser_headers(headers)
                try:
                    sess = requests.Session()
                    sess.verify = False
                    resp = sess.get(dl_url, headers=headers, stream=True, timeout=120)
                    if resp.status_code != 200:
                        sess.close()
                        continue
                    with open(output_path, "wb") as f:
                        for chunk in resp.iter_content(65536):
                            if not chunk:
                                continue
                            f.write(chunk)
                            f.flush()
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            total_written += len(chunk)
                    resp.close()
                    sess.close()
                    if log:
                        log.log("STREAM DONE %s bytes=%d", px, total_written)
                    return
                except Exception:
                    continue

            if log:
                log.log("STREAM FAIL all proxies, written=%d", total_written)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


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
