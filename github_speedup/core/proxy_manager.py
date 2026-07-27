import json
import os
import threading
import time
import dataclasses
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .utils import (
    app_dir, build_proxy_url, strip_scheme, is_valid_proxy_domain,
    apply_browser_headers, find_proxies_file, find_active_proxies_file,
    SHARED_SESSION,
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
    silent: int = 0
    total: int = 0
    silentDomains: List[str] = dataclasses.field(default_factory=list)


class ProxyManager:
    def __init__(self):
        self._mu = threading.Lock()
        self._active_path = find_active_proxies_file()
        self._proxies: List[ProxyItem] = []
        self._silent_list: List[str] = []
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

    def preflight_check(self) -> PreflightResult:
        with self._mu:
            proxies = list(self._proxies)
        available = 0
        silent = 0
        silent_domains = []
        updated = []

        def test(p: ProxyItem):
            result = test_single_proxy(p.domain)
            if result.status == "active":
                return p.domain, result, "active"
            else:
                return p.domain, result, "silent"

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = {pool.submit(test, p): p for p in proxies if p.enabled}
            for future in as_completed(futures):
                domain, result, status = future.result()
                updated.append((domain, result))
                if status == "active":
                    available += 1
                else:
                    silent += 1
                    silent_domains.append(domain)

        with self._mu:
            for domain, result in updated:
                for p in self._proxies:
                    if p.domain == domain:
                        p.scheme = result.scheme
                        p.latency = result.latency
                        p.speed = result.speed
                        p.status = result.status
                        break
            self._sort()
            self._save()
            self._silent_list = silent_domains

        return PreflightResult(
            available=available, silent=silent, total=len(proxies),
            silentDomains=silent_domains,
        )

    def test_all(self):
        with self._mu:
            proxies = list(self._proxies)

        def test(p: ProxyItem):
            result = test_single_proxy(p.domain)
            return p.domain, result

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = {pool.submit(test, p): p for p in proxies}
            for future in as_completed(futures):
                domain, result = future.result()
                self.update(domain,
                            scheme=result.scheme,
                            latency=result.latency,
                            speed=result.speed,
                            status=result.status)

    def test_one(self, domain: str) -> ProxyTestResult:
        result = test_single_proxy(strip_scheme(domain))
        self.update(domain,
                    scheme=result.scheme,
                    latency=result.latency,
                    speed=result.speed,
                    status=result.status)
        return result

    def _sort(self):
        status_order = {"active": 0, "silent": 1, "offline": 2, "checking": 3}
        self._proxies.sort(key=lambda p: (
            status_order.get(p.status, 9),
            -parse_speed_mbps(p.speed) if p.status == "active" else 0,
            parse_latency_ms(p.latency) if p.status == "silent" else 0,
        ))

    def get_silent_list(self) -> List[str]:
        with self._mu:
            return list(self._silent_list)

    def unsilence(self, domain: str):
        raw = strip_scheme(domain)
        with self._mu:
            self._silent_list = [d for d in self._silent_list if d != raw]


def parse_speed_mbps(speed: str) -> float:
    if not speed or speed == "N/A":
        return 0
    s = speed.replace(" Mbps", "")
    try:
        return float(s)
    except ValueError:
        return 0


def parse_latency_ms(latency: str) -> int:
    if not latency or latency == "N/A":
        return 999999
    s = latency.replace(" ms", "")
    try:
        return int(s)
    except ValueError:
        return 999999


def test_single_proxy(domain: str) -> ProxyTestResult:
    raw_domain = strip_scheme(domain)
    for scheme in ("https", "http"):
        proxy_url = build_proxy_url(scheme, raw_domain, PROXY_TEST_URL)
        start = time.time()
        req_headers = {}
        apply_browser_headers(req_headers)
        try:
            resp = SHARED_SESSION.get(
                proxy_url,
                timeout=(8, 15),
                headers=req_headers,
                stream=True,
            )
        except Exception:
            continue
        latency_ms = int((time.time() - start) * 1000)
        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct.lower():
            resp.close()
            continue
        start = time.time()
        total_bytes = 0
        try:
            for chunk in resp.iter_content(chunk_size=32768):
                if chunk:
                    total_bytes += len(chunk)
        except Exception:
            resp.close()
            continue
        resp.close()
        elapsed = time.time() - start
        status = "active"
        speed_str = "N/A"
        if elapsed > 0 and total_bytes > 0:
            speed_mbps = (total_bytes / elapsed) * 8 / 1_000_000
            speed_str = f"{speed_mbps:.1f} Mbps"
            if speed_mbps < 0.1:
                status = "silent"
        if latency_ms > 2000:
            status = "silent"
        return ProxyTestResult(
            domain=raw_domain, scheme=scheme,
            latency=f"{latency_ms} ms", speed=speed_str,
            status=status,
        )
    return ProxyTestResult(
        domain=raw_domain, scheme="",
        latency="N/A", speed="N/A", status="offline",
    )
