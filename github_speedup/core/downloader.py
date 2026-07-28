import os
import threading
import time
import dataclasses
from typing import Callable, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from .utils import (
    SHARED_SESSION, HEAD_SESSION, find_active_proxies_file,
)
from .logger import AccessLogger


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


def get_file_size_via_proxies(proxy_list: List[str], raw_url: str, timeout: int) -> int:
    for proxy in proxy_list:
        if proxy.endswith("/"):
            u = f"{proxy}{raw_url}"
        else:
            u = f"{proxy}/{raw_url}"
        try:
            resp = HEAD_SESSION.head(u, timeout=timeout)
            cl = resp.headers.get("Content-Length")
            resp.close()
            if cl and cl.isdigit():
                return int(cl)
        except Exception:
            continue
    return 0


def start_background_download(
    task: DownloadTask,
    record_success: Optional[Callable] = None,
    record_failure: Optional[Callable] = None,
    on_progress: Optional[Callable] = None,
    task_id: int = 0,
) -> DownloadTask:
    if task.part_size_bytes == 0:
        task.part_size_bytes = 4 * 1024 * 1024
    if task.max_concurrent == 0:
        task.max_concurrent = 20
    if task.max_retry == 0:
        task.max_retry = 3
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
        active_path = find_active_proxies_file()
        with open(active_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        for e in entries:
            if e.get("status") == "active" and e.get("enabled", True):
                s = e.get("scheme", "https")
                d = e.get("domain", "")
                if s and d:
                    proxy_list.append(f"{s}://{d}")
    except Exception:
        pass

    if not proxy_list:
        task.status = "failed"
        cleanup()
        return task

    task.file_name = guess_file_name(task.url)
    output_path = os.path.join(task.save_dir, task.file_name)

    total_bytes = get_file_size_via_proxies(proxy_list, task.url, task.timeout)
    if total_bytes == 0:
        task.status = "failed"
        cleanup()
        return task
    task.total_bytes = total_bytes

    part_size = task.part_size_bytes
    if total_bytes < part_size:
        part_size = total_bytes
    num_parts = (total_bytes + part_size - 1) // part_size

    if log:
        log.log(
            "DOWNLOAD READY %s | %d bytes, %d parts @ %d MB, workers=%d proxies=%d",
            task.url, total_bytes, num_parts, part_size // 1024 // 1024,
            task.max_concurrent, len(proxy_list),
        )

    jobs = []
    for i in range(num_parts):
        start = i * part_size
        end = start + part_size - 1
        if end >= total_bytes:
            end = total_bytes - 1
        jobs.append(PartJob(
            index=i, start=start, end=end,
            proxy=proxy_list[i % len(proxy_list)],
        ))

    speed_history: List[tuple] = []
    hist_lock = threading.Lock()
    raw_downloaded = 0
    confirmed_bytes = 0

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

    results_lock = threading.Lock()
    failed_parts: List[PartJob] = []
    proxy_used: dict[str, int] = {}
    all_done = False
    first_err = Exception("all proxies failed")

    def download_part(job: PartJob) -> tuple:
        nonlocal raw_downloaded
        if cancel_evt.is_set():
            return job.index, Exception("cancelled"), job.proxy, 0
        download_url = f"{job.proxy}/{task.url}"
        headers = {"Range": f"bytes={job.start}-{job.end}"}
        try:
            resp = SHARED_SESSION.get(
                download_url, headers=headers,
                timeout=task.timeout, stream=True,
            )
        except Exception as e:
            return job.index, e, job.proxy, 0
        if resp.status_code not in (200, 206):
            resp.close()
            return job.index, Exception(f"HTTP {resp.status_code}"), job.proxy, 0
        part_file = f"{output_path}.part.{job.index}"
        written = 0
        write_ok = True
        try:
            with open(part_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if cancel_evt.is_set():
                        write_ok = False
                        break
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
                        with hist_lock:
                            raw_downloaded += len(chunk)
            resp.close()
        except Exception as e:
            resp.close()
            return job.index, e, job.proxy, 0
        if not write_ok:
            return job.index, Exception("cancelled"), job.proxy, 0
        return job.index, None, job.proxy, written

    with ThreadPoolExecutor(max_workers=task.max_concurrent) as pool:
        fut_map = {pool.submit(download_part, j): j for j in jobs}
        for future in as_completed(fut_map):
            if cancel_evt.is_set():
                break
            idx, err, proxy, size = future.result()
            domain = proxy
            try:
                domain = urlparse(proxy).hostname or proxy
            except Exception:
                pass
            if err:
                if log:
                    log.log("PARTFAIL %s part=%d err=%v", domain, idx, err)
                with results_lock:
                    failed_parts.append(jobs[idx])
                if record_failure:
                    record_failure(domain)
                first_err = err
            else:
                if log:
                    log.log("PARTOK %s part=%d bytes=%d", domain, idx, size)
                proxy_used[proxy] = proxy_used.get(proxy, 0) + size
                with hist_lock:
                    confirmed_bytes += size
                all_done = True

    if cancel_evt.is_set():
        task.status = "failed"
        cleanup()
        return task

    # Retry failed parts
    if failed_parts:
        if log:
            log.log("RETRY START failed=%d maxRetry=%d", len(failed_parts), task.max_retry)
        for retry_round in range(task.max_retry):
            if cancel_evt.is_set():
                break
            still_failed = []
            if log:
                log.log("RETRY ROUND %d/%d parts=%d", retry_round + 1, task.max_retry, len(failed_parts))
            for fp in failed_parts:
                if cancel_evt.is_set():
                    still_failed.append(fp)
                    break
                retry_ok = False
                for p in proxy_list:
                    if cancel_evt.is_set():
                        break
                    download_url = f"{p}/{task.url}"
                    headers = {"Range": f"bytes={fp.start}-{fp.end}"}
                    try:
                        resp = SHARED_SESSION.get(
                            download_url, headers=headers,
                            timeout=task.timeout, stream=True,
                        )
                    except Exception:
                        continue
                    if resp.status_code not in (200, 206):
                        resp.close()
                        continue
                    part_file = f"{output_path}.part.{fp.index}"
                    written = 0
                    write_ok = True
                    try:
                        with open(part_file, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=65536):
                                if cancel_evt.is_set():
                                    write_ok = False
                                    break
                                if chunk:
                                    f.write(chunk)
                                    written += len(chunk)
                                    with hist_lock:
                                        raw_downloaded += len(chunk)
                        resp.close()
                    except Exception:
                        resp.close()
                        write_ok = False
                    if write_ok and written > 0:
                        proxy_used[p] = proxy_used.get(p, 0) + written
                        all_done = True
                        retry_ok = True
                        domain = p
                        try:
                            domain = urlparse(p).hostname or p
                        except Exception:
                            pass
                        if log:
                            log.log("RETRYOK %s part=%d bytes=%d", domain, fp.index, written)
                        with hist_lock:
                            confirmed_bytes += written
                        break
                if not retry_ok:
                    still_failed.append(fp)
                    if log:
                        log.log("RETRYFAIL part=%d (all proxies exhausted)", fp.index)
            failed_parts = still_failed
            if not failed_parts:
                break

    if not all_done:
        if log:
            log.log("DOWNLOAD FAILED all parts failed: %v", first_err)
        task.status = "failed"
        cleanup()
        return task

    if log:
        log.log("DOWNLOAD COMPLETED %s", task.url)

    # Merge parts
    try:
        with open(output_path, "wb") as out_f:
            buf = bytearray(1024 * 1024)
            for i in range(num_parts):
                part_file = f"{output_path}.part.{i}"
                try:
                    with open(part_file, "rb") as pf:
                        while True:
                            n = pf.readinto(buf)
                            if not n:
                                break
                            out_f.write(buf[:n])
                    os.remove(part_file)
                except FileNotFoundError:
                    continue
    except Exception as e:
        task.status = "failed"
        cleanup()
        return task

    if os.path.isfile(output_path):
        task.total_bytes = os.path.getsize(output_path)
    task.downloaded = task.total_bytes
    task.status = "completed"

    if on_progress:
        on_progress(ProgressData(
            task_id=task_id,
            downloaded=confirmed_bytes,
            total_bytes=total_bytes,
            speed=calc_speed(),
        ))

    if record_success:
        if log:
            log.log("RECORDING %d proxies:", len(proxy_used))
        for p, bs in proxy_used.items():
            if bs == 0:
                continue
            domain = p
            try:
                domain = urlparse(p).hostname or p
            except Exception:
                pass
            if log:
                log.log("RECORD %s bytes=%d", domain, bs)
            s = calc_speed()
            record_success(domain, bs, s)

    cleanup()
    return task
