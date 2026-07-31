import json
import os
import threading
import time
import dataclasses
import queue
from typing import List, Optional, Callable
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed

from .utils import (
    app_dir, build_proxy_url, strip_scheme, is_valid_proxy_domain,
    apply_browser_headers, find_proxies_file, find_active_proxies_file,
    SHARED_SESSION, get_viper, BROWSER_HEADERS,
)

PROXY_TEST_URL = "https://github.com/zxc74105/ceshi/blob/main/speedtest.txt"

DEFAULT_PROXIES = [
    "gh-proxy.com", "ghproxy.net", "git.yylx.win", "gh.927223.xyz",
    "gh.felicity.ac.cn", "tvv.tw", "jiashu.1win.eu.org", "gh.inkchills.cn",
    "gh.my-website.ccwu.cc", "gh.07150721.xyz", "cfgh.ikgy.top",
    "xsadwsd.kdns.fr", "ghproxy.felicity.land", "gh-proxy.org",
    "v4.gh-proxy.org", "v6.gh-proxy.org", "cdn.gh-proxy.org",
    "edgeone.gh-proxy.org", "hk.gh-proxy.org", "gh-proxy.cn",
    "gitproxy.mrhjx.cn", "gh.sixyin.com", "gh.monlor.com", "ghfast.top",
    "gh.jasonzeng.dev", "gp.zkitefly.eu.org", "ghproxy.monkeyray.net",
    "gh.noki.icu", "g.blfrp.cn",
]


@dataclasses.dataclass
class ProxyItem:
    domain: str = ""
    scheme: str = "https"
    enabled: bool = True
    status: str = "active"
    latency: str = ""
    speed: str = ""


@dataclasses.dataclass
class ProxyTestResult:
    domain: str = ""
    scheme: str = ""
    latency: str = ""
    speed: str = ""
    status: str = ""


@dataclasses.dataclass
class PreflightResult:
    available: int = 0
    total: int = 0


class ProxyManager:
    def __init__(self):
        self._mu = threading.Lock()
        self._active_path = find_active_proxies_file()
        self._proxies: List[ProxyItem] = []
        self._load()

    def _load(self):
        try:
            with open(self._active_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                items = []
                for entry in data:
                    if isinstance(entry, dict):
                        domain = entry.get("domain", "")
                        scheme = entry.get("scheme", "")
                        if not scheme and ("://" in domain):
                            parts = domain.split("://", 1)
                            scheme = parts[0]
                            domain = parts[1]
                        items.append(ProxyItem(
                            domain=domain,
                            scheme=scheme or entry.get("scheme", "https"),
                            enabled=entry.get("enabled", True),
                            status=entry.get("status", "active"),
                            latency=entry.get("latency", ""),
                            speed=entry.get("speed", ""),
                        ))
                    elif isinstance(entry, str):
                        items.append(ProxyItem(domain=entry))
                self._proxies = items
                return
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        self._proxies = self._load_defaults()
        self._save()

    def _load_defaults(self) -> List[ProxyItem]:
        domains = []
        src_path = find_proxies_file()
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                domains = data
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        if not domains:
            domains = DEFAULT_PROXIES
            with open(src_path, "w", encoding="utf-8") as f:
                json.dump(domains, f, ensure_ascii=False, indent=2)
        seen = set()
        items = []
        for d in domains:
            d = d.strip()
            d = strip_scheme(d)
            if not d or d in seen or not is_valid_proxy_domain(d):
                continue
            seen.add(d)
            items.append(ProxyItem(domain=d, scheme="https", enabled=True, status="active"))
        return items

    def _save(self):
        data = []
        for p in self._proxies:
            data.append(dataclasses.asdict(p))
        with open(self._active_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> List[ProxyItem]:
        with self._mu:
            return list(self._proxies)

    def get_active(self) -> List[str]:
        with self._mu:
            result = []
            for p in self._proxies:
                if p.status == "active" and p.enabled and p.scheme:
                    result.append(build_proxy_url(p.scheme, p.domain))
            return result

    def get_by_domain(self, domain: str) -> Optional[ProxyItem]:
        raw = strip_scheme(domain)
        with self._mu:
            for p in self._proxies:
                if p.domain == raw:
                    return p
        return None

    def update(self, domain: str, **kwargs):
        raw = strip_scheme(domain)
        with self._mu:
            for p in self._proxies:
                if p.domain == raw:
                    for k, v in kwargs.items():
                        if hasattr(p, k):
                            setattr(p, k, v)
                    break
            self._save()

    def toggle(self, domain: str, enabled: bool):
        self.update(domain, enabled=enabled)

    def import_from_file(self, file_path: str) -> int:
        lines = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(line)
        except FileNotFoundError:
            return 0
        count = 0
        with self._mu:
            existing = {p.domain for p in self._proxies}
            for line in lines:
                line = strip_scheme(line)
                if not line or line in existing or not is_valid_proxy_domain(line):
                    continue
                self._proxies.append(ProxyItem(domain=line, enabled=True, status="active"))
                existing.add(line)
                count += 1
            if count > 0:
                self._save()
        return count

    def export_to_file(self, file_path: str):
        with self._mu:
            lines = [p.domain for p in self._proxies]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def delete_domains(self, domains: List[str]):
        raw_set = {strip_scheme(d) for d in domains}
        with self._mu:
            self._proxies = [p for p in self._proxies if p.domain not in raw_set]
            self._save()

    @staticmethod
    def _run_with_timeout(tasks: list, timeout: int = 180):
        """用 daemon 线程并发执行，总超时后返回已完成的结果"""
        q = queue.Queue()
        for t in tasks:
            q.put(t)
        results = []
        lock = threading.Lock()

        def worker():
            while True:
                try:
                    t = q.get_nowait()
                except queue.Empty:
                    break
                try:
                    r = t()
                except Exception:
                    continue
                with lock:
                    results.append(r)

        n = min(30, len(tasks))
        threads = [threading.Thread(target=worker, daemon=True) for _ in range(n)]
        for th in threads:
            th.start()
        deadline = time.time() + timeout
        for th in threads:
            remaining = deadline - time.time()
            if remaining > 0:
                th.join(timeout=remaining)
        return results

    def preflight_check(self, on_result=None) -> PreflightResult:
        with self._mu:
            proxies = list(self._proxies)
            # 重置所有状态为 active，超时未测的代理保持乐观默认
            for p in self._proxies:
                p.status = "active"
                p.latency = ""
                p.speed = ""
        available = 0

        def test(p: ProxyItem):
            result = test_single_proxy(p.domain)
            return p.domain, result

        results = self._run_with_timeout(
            [lambda p=p: test(p) for p in proxies if p.enabled], timeout=180,
        )

        for domain, result in results:
            with self._mu:
                for p in self._proxies:
                    if p.domain == domain:
                        p.scheme = result.scheme
                        p.latency = result.latency
                        p.speed = result.speed
                        p.status = result.status
                        break
            if result.status == "active":
                available += 1
            if on_result:
                on_result(domain, result)

        with self._mu:
            self._sort()
            self._save()

        return PreflightResult(
            available=available, total=len(proxies),
        )

    def test_all(self, on_result=None):
        with self._mu:
            proxies = list(self._proxies)
            for p in self._proxies:
                p.status = "active"
                p.latency = ""
                p.speed = ""

        def test(p: ProxyItem):
            result = test_single_proxy(p.domain)
            return p.domain, result

        results = self._run_with_timeout(
            [lambda p=p: test(p) for p in proxies if p.enabled], timeout=180,
        )

        for domain, result in results:
            self.update(domain,
                        scheme=result.scheme,
                        latency=result.latency,
                        speed=result.speed,
                        status=result.status)
            if on_result:
                on_result(domain, result)

    def test_one(self, domain: str) -> ProxyTestResult:
        result = test_single_proxy(strip_scheme(domain))
        self.update(domain,
                    scheme=result.scheme,
                    latency=result.latency,
                    speed=result.speed,
                    status=result.status)
        return result

    def _sort(self):
        self._proxies.sort(key=lambda p: (
            0 if p.status == "active" else 1,
            parse_speed_secs(p.speed) if p.status == "active" else 999999,
        ))


def parse_speed_secs(speed: str) -> float:
    if not speed or speed in ("-", "N/A"):
        return 999999
    s = speed.replace("s", "")
    try:
        return float(s)
    except ValueError:
        return 0


PROXY_HARD_TIMEOUT = 15  # seconds (unused, kept for reference)
PROXY_SPEED_TEST_URL = "https://github.com/zxc74105/ceshi/raw/main/speedtest_200k.bin"
PROXY_SPEED_TIMEOUT = 60  # seconds, 200KB 文件测速超时

def _viper_download(url: str):
    """vipertls 下载，直接在当前线程用缓存的客户端，返回 (bytes_len, seconds) 或 None"""
    try:
        v = get_viper()
        t0 = time.time()
        r = v.get(url, headers=BROWSER_HEADERS)
        secs = time.time() - t0
        ct = r.headers.get("Content-Type", "")
        if "text/html" in ct.lower():
            return None
        return len(r.content), secs
    except Exception:
        return None


def _speed_test(url: str, timeout: int):
    """用 vipertls 下载 200KB 测速文件，返回 body 传输秒数或 None"""
    try:
        v = get_viper()
        t0 = time.time()
        r = v.get(url, headers=BROWSER_HEADERS)
        secs = time.time() - t0
        ct = r.headers.get("Content-Type", "")
        if "text/html" in ct.lower():
            return None
        if len(r.content) > 0:
            return secs
    except Exception:
        pass
    return None


def test_single_proxy(domain: str) -> ProxyTestResult:
    raw_domain = strip_scheme(domain)
    for scheme in ("https", "http"):
        proxy_url = build_proxy_url(scheme, raw_domain, PROXY_TEST_URL)
        viper = get_viper()
        if viper is not None:
            # Phase 1: 连通性（34 字节）
            r = _viper_download(proxy_url)
            if r is None:
                continue
            _, conn_secs = r
            result = ProxyTestResult(
                domain=raw_domain, scheme=scheme,
                latency=f"{int(conn_secs * 1000)} ms", speed="-",
                status="active",
            )
            # Phase 2: 网速测（1MB，只算 body 下载时间）
            speed_url = build_proxy_url(scheme, raw_domain, PROXY_SPEED_TEST_URL)
            body_secs = _speed_test(speed_url, PROXY_SPEED_TIMEOUT)
            if body_secs is not None:
                result.speed = f"{body_secs:.1f}s"
            return result
        try:
            total_start = time.time()
            resp = SHARED_SESSION.get(
                proxy_url, timeout=5, headers=BROWSER_HEADERS, stream=True,
            )
        except Exception:
            continue
        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct.lower():
            resp.close()
            continue
        try:
            total_bytes = 0
            for chunk in resp.iter_content(chunk_size=32768):
                if chunk:
                    total_bytes += len(chunk)
        except Exception:
            resp.close()
            continue
        resp.close()
        total_secs = time.time() - total_start
        speed_str = "-"
        if total_secs > 0 and total_bytes > 0:
            speed_str = f"{total_secs:.1f}s"
        return ProxyTestResult(
            domain=raw_domain, scheme=scheme,
            latency=f"{int(total_secs * 1000)} ms", speed=speed_str,
            status="active",
        )
    return ProxyTestResult(
        domain=raw_domain, scheme="",
        latency="-", speed="-", status="offline",
    )
