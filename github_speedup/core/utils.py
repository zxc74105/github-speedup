import os
import sys
import requests


SHARED_SESSION = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=100,
    pool_maxsize=100,
    max_retries=0,
)
SHARED_SESSION.mount("https://", adapter)
SHARED_SESSION.mount("http://", adapter)
SHARED_SESSION.verify = False
SHARED_SESSION.stream = True

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
    "Connection": "keep-alive",
}


def apply_browser_headers(headers: dict):
    for k, v in BROWSER_HEADERS.items():
        if k not in headers:
            headers[k] = v


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def find_proxies_file() -> str:
    candidates = [
        os.path.join(app_dir(), "proxies.json"),
        "proxies.json",
    ]
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(sys._MEIPASS, "proxies.json"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return os.path.join(app_dir(), "proxies.json")


def find_active_proxies_file() -> str:
    return os.path.join(app_dir(), "proxies-active.json")


def is_valid_proxy_domain(domain: str) -> bool:
    if not domain:
        return False
    if any(ch in domain for ch in " \t\n\r"):
        return False
    clean = strip_scheme(domain)
    if not clean:
        return False
    if "." not in clean:
        return False
    if any(ch in clean for ch in "=/\\#@!~`\"'<>{}[]|"):
        return False
    for ch in clean:
        if ord(ch) > 127:
            return False
    return True


def strip_scheme(domain: str) -> str:
    if "://" in domain:
        return domain.split("://", 1)[1]
    return domain


def build_proxy_url(scheme: str, domain: str, target_url: str = "") -> str:
    if not scheme:
        scheme = "https"
    if not target_url:
        return f"{scheme}://{domain}"
    return f"{scheme}://{domain}/{target_url}"
