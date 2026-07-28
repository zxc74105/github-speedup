import json
import os
import shutil
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Optional

from ..core.utils import (
    SHARED_SESSION, apply_browser_headers, build_proxy_url,
    app_dir,
)
from ..core.downloader import DownloadTask, start_background_download, guess_file_name
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
            log.log("API DOWNLOAD %s from %s", target_url, self.client_address[0])

        temp_dir = tempfile.mkdtemp(prefix="gs_proxy_")
        try:
            task = DownloadTask(
                url=target_url,
                save_dir=temp_dir,
                part_size_bytes=4 * 1024 * 1024,
                max_concurrent=20,
                max_retry=3,
                timeout=30,
            )

            if self.records_manager:
                def record_success(domain, bs, spd):
                    self.records_manager.record_success(domain, bs, spd)
                def record_failure(domain):
                    self.records_manager.record_failure(domain)
            else:
                record_success = None
                record_failure = None

            result = start_background_download(task, record_success, record_failure)

            if result.status != "completed":
                self.send_error(502, f"download failed: {result.status}")
                return

            file_name = result.file_name or guess_file_name(target_url)
            output_path = os.path.join(temp_dir, file_name)
            if not os.path.isfile(output_path):
                self.send_error(502, "file not found after download")
                return

            file_size = os.path.getsize(output_path)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
            self.send_header("Content-Length", str(file_size))
            self.send_header("X-Download-Mode", "multi-threaded-20x")
            self.end_headers()

            with open(output_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
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
