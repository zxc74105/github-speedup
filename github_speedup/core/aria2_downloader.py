import json
import os
import subprocess
import threading
import time
import urllib.request
import urllib.error
from typing import Optional

from .utils import app_dir, find_active_proxies_file

RPC_PORT = 6802
LOCAL_PROXY_PORT = 6801


class Aria2Manager:
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._running = False

    def _find_binary(self) -> Optional[str]:
        candidates = [
            os.path.join(app_dir(), "bin", "aria2c.exe"),
            os.path.join(app_dir(), "aria2c.exe"),
            "aria2c.exe",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return os.path.abspath(p)
        return None

    def start(self, save_dir: str):
        with self._lock:
            if self._running:
                return
            binary = self._find_binary()
            if not binary:
                return
            args = [
                binary,
                "--enable-rpc",
                f"--rpc-listen-port={RPC_PORT}",
                "--rpc-listen-all=false",
                "--max-connection-per-server=16",
                "--split=16",
                "--min-split-size=1M",
                "--uri-selector=feedback",
                "--max-concurrent-downloads=5",
                "--continue=true",
                "--quiet=true",
                "--async-dns=false",
                "--allow-overwrite=true",
                "--auto-file-renaming=false",
                "--dir", save_dir,
            ]
            try:
                self._process = subprocess.Popen(
                    args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self._running = True
            except FileNotFoundError:
                self._process = None
                self._running = False

    def stop(self):
        with self._lock:
            if self._process:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except Exception:
                    pass
                self._process = None
            self._running = False

    @property
    def running(self) -> bool:
        if not self._running:
            return False
        if self._process and self._process.poll() is not None:
            self._running = False
            return False
        return True

    def _rpc(self, method: str, params: list, retries: int = 3) -> dict:
        for attempt in range(retries):
            data = json.dumps({"jsonrpc": "2.0", "id": "1", "method": method, "params": params}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{RPC_PORT}/jsonrpc",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                return json.loads(resp.read().decode())
            except (urllib.error.URLError, json.JSONDecodeError, OSError):
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return {"error": "rpc failed"}
        return {"error": "rpc failed"}

    def add_download(self, urls: list[str], filename: str) -> Optional[str]:
        result = self._rpc("aria2.addUri", [
            urls,
            {"out": filename, "split": min(16, len(urls))},
        ])
        if "error" in result:
            return None
        return result.get("result")

    def tell_status(self, gid: str) -> dict:
        result = self._rpc("aria2.tellStatus", [gid])
        return result.get("result", {})

    def tell_active(self) -> list:
        result = self._rpc("aria2.tellActive", [])
        return result.get("result", [])

    def remove(self, gid: str):
        self._rpc("aria2.remove", [gid])

    def pause(self, gid: str):
        self._rpc("aria2.pause", [gid])

    def unpause(self, gid: str):
        self._rpc("aria2.unpause", [gid])

    def build_mirror_urls(self, target_url: str) -> list[str]:
        urls = []
        try:
            with open(find_active_proxies_file(), "r", encoding="utf-8") as f:
                entries = json.load(f)
            for e in entries:
                if e.get("status") == "active" and e.get("enabled", True):
                    scheme = e.get("scheme", "https")
                    domain = e.get("domain", "")
                    if scheme and domain:
                        urls.append(f"{scheme}://{domain}/{target_url}")
        except Exception:
            pass
        return urls

    def parse_progress(self, status: dict) -> dict:
        total = int(status.get("totalLength", "0"))
        completed = int(status.get("completedLength", "0"))
        speed = int(status.get("downloadSpeed", "0"))
        return {
            "total_bytes": total,
            "downloaded": completed,
            "speed": speed,
            "progress": (completed / total * 100) if total > 0 else 0,
            "status": status.get("status", ""),
            "gid": status.get("gid", ""),
        }


_global_aria2 = Aria2Manager()
_global_lock = threading.Lock()


def get_aria2() -> Aria2Manager:
    return _global_aria2
