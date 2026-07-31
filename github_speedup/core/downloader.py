import os
import re
import threading
import time
import dataclasses
from typing import Callable, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from .utils import (
    SHARED_SESSION, apply_browser_headers, find_active_proxies_file,
)
from .aria2_downloader import get_aria2
from .logger import AccessLogger


_aria2_inited = False
_aria2_lock = threading.Lock()


def ensure_download_backend(save_dir: str):
    global _aria2_inited
    if _aria2_inited:
        return True
    with _aria2_lock:
        if _aria2_inited:
            return True
        aria2 = get_aria2()
        aria2.start(save_dir)
        _aria2_inited = True
        return aria2.running


def shutdown_backend():
    global _aria2_inited
    aria2 = get_aria2()
    aria2.stop()
    _aria2_inited = False


@dataclasses.dataclass
class DownloadTask:
    url: str = ""
    save_dir: str = ""
    file_name: str = ""
    total_bytes: int = 0
    downloaded: int = 0
    part_size_bytes: int = 4 * 1024 * 1024
    max_concurrent: int = 20
    max_retry: int = 3
    timeout: int = 30
    status: str = ""
    speed: float = 0.0
    eta: str = ""
    created_at: float = 0.0


@dataclasses.dataclass
class ProgressData:
    task_id: int = 0
    downloaded: int = 0
    total_bytes: int = 0
    speed: float = 0.0
    worker_id: int = 0
    worker_proxy: str = ""
    worker_speed: float = 0.0
    part_done: bool = False
    part_failed: bool = False
    proxy_domain: str = ""


@dataclasses.dataclass
class PartJob:
    index: int
    start: int
    end: int
    proxy: str


_tasks_lock = threading.Lock()
_next_id = 1
_cancel_events: dict[int, threading.Event] = {}


def cancel_download(task_id: int):
    with _tasks_lock:
        evt = _cancel_events.get(task_id)
        if evt:
            evt.set()


def guess_file_name(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    name = os.path.basename(parsed.path)
    if not name or name in (".", "/", ""):
        return "downloaded_file"
    return name


def _probe_size(proxy: str, raw_url: str, timeout: int) -> int:
    if proxy.endswith("/"):
        u = f"{proxy}{raw_url}"
    else:
        u = f"{proxy}/{raw_url}"
    headers = {"Accept-Encoding": "identity", "Range": "bytes=0-0"}
    apply_browser_headers(headers)
    try:
        resp = SHARED_SESSION.get(u, headers=headers, timeout=timeout)
        cr = resp.headers.get("Content-Range", "")
        cl = resp.headers.get("Content-Length", "")
        resp.close()
        if resp.status_code == 206 and cr:
            try:
                total = int(cr.rsplit("/", 1)[1])
                if total > 0:
                    return total
            except ValueError:
                pass
        if cl and cl.isdigit():
            total = int(cl)
            if total > 0:
                return total
    except Exception:
        pass
    return 0


def get_file_size_via_proxies(proxy_list: List[str], raw_url: str, timeout: int) -> int:
    per_probe_timeout = min(timeout, 3)

    def sp(e: str) -> float:
        return 0.0

    ordered = list(proxy_list)
    try:
        import json
        from .utils import find_active_proxies_file
        entries = {}
        with open(find_active_proxies_file(), "r", encoding="utf-8") as f:
            for e in json.load(f):
                if e.get("domain"):
                    entries[e.get("domain")] = e
        def speed_of(p: str) -> float:
            d = p.split("://", 1)[-1]
            e = entries.get(d) or entries.get(p, {})
            s = str(e.get("speed", "99")).rstrip("s")
            try:
                return float(s) if s not in ("-", "", "N/A") else 99.0
            except ValueError:
                return 99.0
        ordered.sort(key=speed_of)
    except Exception:
        pass
    ordered = ordered[:40]

    best = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = {ex.submit(_probe_size, p, raw_url, per_probe_timeout): p for p in ordered}
        done = 0
        for fut in as_completed(futures):
            try:
                n = fut.result()
            except Exception:
                n = 0
            done += 1
            if n > best:
                best = n
            if best >= 2048 or done >= len(futures):
                break
    return best


def _extract_used_proxy(status: dict) -> str:
    try:
        for f in status.get("files", []):
            for u in f.get("uris", []):
                if u.get("status") == "used":
                    raw = u.get("uri", "")
                    host = urlparse(raw).hostname or ""
                    if host and host != "127.0.0.1":
                        return host
    except Exception:
        pass
    return ""


def _aria2_download(
    task: DownloadTask,
    record_success: Optional[Callable] = None,
    record_failure: Optional[Callable] = None,
    on_progress: Optional[Callable] = None,
    task_id: int = 0,
) -> DownloadTask:
    aria2 = get_aria2()
    if not aria2.running:
        task.status = "failed"
        return task

    task.file_name = guess_file_name(task.url)
    task.status = "downloading"

    urls = aria2.build_mirror_urls(task.url)
    if not urls:
        task.status = "failed"
        return task

    gid = aria2.add_download(urls, task.file_name)
    if gid is None:
        task.status = "failed"
        return task

    log = AccessLogger.get()
    if log:
        log.log("ARIA2 START gid=%s url=%s mirrors=%d", gid, task.url, len(urls))

    cancel_evt = threading.Event()
    with _tasks_lock:
        _cancel_events[task_id] = cancel_evt

    poll_interval = 0.5
    last_downloaded = 0
    last_time = time.time()
    stall_start: Optional[float] = None

    while not cancel_evt.is_set():
        time.sleep(poll_interval)
        status = aria2.tell_status(gid)
        if not status:
            continue

        s = status.get("status", "")
        total = int(status.get("totalLength", "0"))
        completed = int(status.get("completedLength", "0"))
        speed = int(status.get("downloadSpeed", "0"))

        task.total_bytes = total
        task.downloaded = completed
        task.speed = speed

        if on_progress:
            on_progress(ProgressData(
                task_id=task_id,
                downloaded=completed,
                total_bytes=total,
                speed=speed,
            ))

        now = time.time()
        if completed > last_downloaded:
            stall_start = None
        elif s == "active":
            if stall_start is None:
                stall_start = now
            elif now - stall_start > task.timeout:
                if log:
                    log.log("ARIA2 STALL timeout gid=%s", gid)
                break

        last_downloaded = completed
        last_time = now

        if s == "complete":
            task.status = "completed"
            task.downloaded = total
            if log:
                log.log("ARIA2 DONE gid=%s bytes=%d speed=%d", gid, total, speed)
            if record_success:
                used_domains = set()
                try:
                    for f in status.get("files", []):
                        for u in f.get("uris", []):
                            raw = u.get("uri", "")
                            host = urlparse(raw).hostname or ""
                            if host and host != "127.0.0.1":
                                used_domains.add(host)
                except Exception:
                    pass
                if used_domains:
                    share = total // len(used_domains)
                    for domain in used_domains:
                        record_success(domain, share, speed)
            break
        elif s == "error":
            task.status = "failed"
            if record_failure:
                used = _extract_used_proxy(status)
                if used:
                    record_failure(used)
            if log:
                err = status.get("errorMessage", "unknown")
                log.log("ARIA2 FAIL gid=%s err=%s", gid, err)
            break
        elif s in ("removed", "paused"):
            task.status = "cancelled"
            break

    with _tasks_lock:
        _cancel_events.pop(task_id, None)

    if cancel_evt.is_set() and task.status == "downloading":
        aria2.remove(gid)
        task.status = "failed"

    return task


def _legacy_download(
    task: DownloadTask,
    record_success: Optional[Callable] = None,
    record_failure: Optional[Callable] = None,
    on_progress: Optional[Callable] = None,
    task_id: int = 0,
) -> DownloadTask:
    if task.timeout == 0:
        task.timeout = 30

    task.status = "preparing"
    task.created_at = time.time()

    cancel_evt = threading.Event()
    with _tasks_lock:
        _cancel_events[task_id] = cancel_evt

    def cleanup():
        cancel_evt.set()
        with _tasks_lock:
            _cancel_events.pop(task_id, None)

    log = AccessLogger.get()

    proxy_list = []
    try:
        import json
        with open(find_active_proxies_file(), "r", encoding="utf-8") as f:
            entries = json.load(f)
        active = []
        for e in entries:
            if e.get("status") == "active" and e.get("enabled", True):
                s = e.get("scheme", "https")
                d = e.get("domain", "")
                if s and d:
                    active.append((f"{s}://{d}", e))

        def _speed_key(item):
            raw = str(item[1].get("speed", "999")).rstrip("s")
            try:
                return float(raw)
            except Exception:
                return 999.0

        active.sort(key=_speed_key)
        proxy_list = [p for p, _ in active]
    except Exception:
        pass

    if not proxy_list:
        task.status = "failed"
        cleanup()
        return task

    task.file_name = guess_file_name(task.url)
    output_path = os.path.join(task.save_dir, task.file_name)

    speed_history: List[tuple] = []
    hist_lock = threading.Lock()
    confirmed_bytes = 0
    proxy_used: dict[str, int] = {}
    proxy_lock = threading.Lock()
    total_bytes = 0
    task.total_bytes = 0

    def start_probe():
        probed = get_file_size_via_proxies(proxy_list, task.url, min(task.timeout, 10))
        nonlocal total_bytes
        if probed > total_bytes:
            total_bytes = probed
            task.total_bytes = probed
            if log:
                log.log("PROBE SIZE %d bytes (proxies=%d)", probed, len(proxy_list))

    probe_thread = threading.Thread(target=start_probe, daemon=True)
    probe_thread.start()

    def calc_speed() -> float:
        now = time.time()
        with hist_lock:
            speed_history.append((now, confirmed_bytes))
            while len(speed_history) > 1 and now - speed_history[0][0] > 10:
                speed_history.pop(0)
            if len(speed_history) > 1:
                d = speed_history[-1][0] - speed_history[0][0]
                if d > 0:
                    return (speed_history[-1][1] - speed_history[0][1]) / d
        return 0.0

    task.status = "downloading"

    def progress_ticker():
        while not cancel_evt.is_set():
            time.sleep(0.5)
            with hist_lock:
                d = confirmed_bytes
            s = calc_speed()
            if on_progress:
                on_progress(ProgressData(
                    task_id=task_id,
                    downloaded=d,
                    total_bytes=total_bytes,
                    speed=s,
                ))

    ticker_thread = threading.Thread(target=progress_ticker, daemon=True)
    ticker_thread.start()

    per_proxy_timeout = min(task.timeout, 15)

    def download_via(proxy: str) -> bool:
        nonlocal confirmed_bytes, total_bytes
        dl_url = f"{proxy}/{task.url}"
        headers = {"Accept-Encoding": "identity"}
        apply_browser_headers(headers)
        resp = None
        try:
            resp = SHARED_SESSION.get(dl_url, headers=headers, timeout=per_proxy_timeout, stream=True)
            if resp.status_code not in (200, 206):
                return False
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit():
                n = int(cl)
                if n > total_bytes:
                    total_bytes = n
                    task.total_bytes = n
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if cancel_evt.is_set():
                        return False
                    if chunk:
                        f.write(chunk)
                        with hist_lock:
                            confirmed_bytes += len(chunk)
            return True
        except Exception:
            return False
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

    def dl_slice(proxy: str, start: int, end: int) -> bool:
        nonlocal confirmed_bytes
        dl_url = f"{proxy}/{task.url}"
        headers = {"Accept-Encoding": "identity", "Range": f"bytes={start}-{end - 1}"}
        apply_browser_headers(headers)
        resp = None
        try:
            resp = SHARED_SESSION.get(dl_url, headers=headers, timeout=per_proxy_timeout, stream=True)
            if resp.status_code not in (200, 206):
                return False
            with open(output_path, "r+b") as f:
                f.seek(start)
                for chunk in resp.iter_content(chunk_size=65536):
                    if cancel_evt.is_set():
                        return False
                    if chunk:
                        f.write(chunk)
                        with hist_lock:
                            confirmed_bytes += len(chunk)
            return True
        except Exception:
            return False
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

    success = False
    probe_deadline = time.time() + min(task.timeout, 10)
    while total_bytes <= 0 and time.time() < probe_deadline and not cancel_evt.is_set():
        time.sleep(0.2)

    if total_bytes > 0 and not cancel_evt.is_set():
        import math
        try:
            with open(output_path, "wb") as f:
                f.truncate(total_bytes)
        except Exception:
            total_bytes = 0

    if total_bytes > 0:
        slice_size = max(4 * 1024 * 1024, math.ceil(total_bytes / 8))
        slice_jobs = []
        for start in range(0, total_bytes, slice_size):
            end = min(start + slice_size, total_bytes)
            slice_jobs.append((start, end))
        k = min(len(proxy_list), len(slice_jobs))
        if k <= 0:
            success = False
        else:
            results: dict = {}
            results_lock = threading.Lock()
            slice_threads = []

            def worker(sl_idx: int):
                start, end = slice_jobs[sl_idx]
                proxy = proxy_list[sl_idx % k]
                ok = dl_slice(proxy, start, end)
                used = proxy
                if not ok and not cancel_evt.is_set():
                    for p2 in proxy_list:
                        if p2 == proxy:
                            continue
                        if cancel_evt.is_set():
                            break
                        if log:
                            log.log("SLICE %d RETRY %s", sl_idx, urlparse(p2).hostname or p2)
                        if dl_slice(p2, start, end):
                            ok = True
                            used = p2
                            break
                with results_lock:
                    results[sl_idx] = ok
                    if ok:
                        with proxy_lock:
                            proxy_used[used] = proxy_used.get(used, 0) + (end - start)
                        if log:
                            log.log("SLICE %d OK %s bytes=%d", sl_idx, urlparse(used).hostname or used, end - start)

            for sl_idx in range(len(slice_jobs)):
                t = threading.Thread(target=worker, args=(sl_idx,), daemon=True)
                slice_threads.append(t)
                t.start()
            for t in slice_threads:
                t.join()
            success = (len(results) == len(slice_jobs)) and all(results.values()) and not cancel_evt.is_set()
            if success and os.path.isfile(output_path):
                if os.path.getsize(output_path) != total_bytes:
                    success = False
    else:
        for p in proxy_list:
            if cancel_evt.is_set():
                break
            try:
                if os.path.isfile(output_path):
                    os.remove(output_path)
            except Exception:
                pass
            if log:
                log.log("TRY %s", urlparse(p).hostname or p)
            if download_via(p):
                success = True
                domain = urlparse(p).hostname or p
                if log:
                    log.log("PROXYOK %s bytes=%d", domain, confirmed_bytes)
                with proxy_lock:
                    proxy_used[p] = proxy_used.get(p, 0) + confirmed_bytes
                break
            else:
                if log:
                    log.log("PROXYFAIL %s", urlparse(p).hostname or p)
                if record_failure:
                    record_failure(urlparse(p).hostname or p)

    if not success:
        if cancel_evt.is_set():
            task.status = "failed"
        else:
            task.status = "failed"
        cleanup()
        return task

    if os.path.isfile(output_path):
        task.total_bytes = os.path.getsize(output_path)
    task.downloaded = task.total_bytes
    task.status = "completed"
    task.speed = calc_speed()

    if on_progress:
        on_progress(ProgressData(
            task_id=task_id,
            downloaded=task.downloaded,
            total_bytes=task.total_bytes,
            speed=task.speed,
        ))

    if record_success:
        for p, bs in proxy_used.items():
            if bs == 0:
                continue
            domain = urlparse(p).hostname or p
            if log:
                log.log("RECORD %s bytes=%d", domain, bs)
            record_success(domain, bs, task.speed)

    cleanup()
    return task


def start_background_download(
    task: DownloadTask,
    record_success: Optional[Callable] = None,
    record_failure: Optional[Callable] = None,
    on_progress: Optional[Callable] = None,
    task_id: int = 0,
) -> DownloadTask:
    result = _legacy_download(task, record_success, record_failure, on_progress, task_id)
    if result.status == "completed":
        return result
    backend_ok = ensure_download_backend(task.save_dir)
    if backend_ok:
        aria2 = get_aria2()
        result = _aria2_download(task, record_success, record_failure, on_progress, task_id)
        if result.status != "failed":
            if os.path.isfile(os.path.join(task.save_dir, task.file_name)):
                result.total_bytes = os.path.getsize(os.path.join(task.save_dir, task.file_name))
                result.downloaded = result.total_bytes
            return result
    return result
