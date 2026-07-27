import json
import os
import threading
import dataclasses
from typing import List
from datetime import datetime

from .utils import app_dir


@dataclasses.dataclass
class ProxyRecord:
    domain: str = ""
    successCount: int = 0
    totalBytes: int = 0
    averageSpeed: float = 0.0
    failCount: int = 0
    firstUsedAt: str = ""
    lastUsedAt: str = ""
    speedHistory: List[float] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TaskInfo:
    id: int = 0
    url: str = ""
    fileName: str = ""
    saveDir: str = ""
    totalBytes: int = 0
    downloaded: int = 0
    speed: float = 0.0
    eta: str = ""
    status: str = ""
    progress: float = 0.0
    createdAt: str = ""


class RecordsManager:
    def __init__(self):
        self._mu = threading.Lock()
        self._path = os.path.join(app_dir(), "proxy-records.json")
        self._records: List[ProxyRecord] = []
        self._load()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._records = []
                for entry in data:
                    if isinstance(entry, dict):
                        self._records.append(ProxyRecord(**entry))
                return
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        self._records = []

    def _save(self):
        data = [dataclasses.asdict(r) for r in self._records]
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> List[ProxyRecord]:
        with self._mu:
            sorted_recs = sorted(
                self._records,
                key=lambda r: (-r.successCount, -r.averageSpeed),
            )
            return list(sorted_recs)

    def record_success(self, domain: str, bytes_count: int, speed: float):
        now = datetime.now().isoformat()
        with self._mu:
            for r in self._records:
                if r.domain == domain:
                    r.successCount += 1
                    r.totalBytes += bytes_count
                    r.lastUsedAt = now
                    if r.successCount > 1:
                        total_speed = r.averageSpeed * (r.successCount - 1) + speed
                        r.averageSpeed = total_speed / r.successCount
                    else:
                        r.averageSpeed = speed
                    r.speedHistory.append(speed)
                    if len(r.speedHistory) > 100:
                        r.speedHistory = r.speedHistory[-100:]
                    self._save()
                    return
            self._records.append(ProxyRecord(
                domain=domain, successCount=1, totalBytes=bytes_count,
                averageSpeed=speed, firstUsedAt=now, lastUsedAt=now,
                speedHistory=[speed],
            ))
            self._save()

    def record_failure(self, domain: str):
        with self._mu:
            for r in self._records:
                if r.domain == domain:
                    r.failCount += 1
                    self._save()
                    return

    def delete_domains(self, domains: list):
        domain_set = set(domains)
        with self._mu:
            self._records = [r for r in self._records if r.domain not in domain_set]
            self._save()

    def clear(self):
        with self._mu:
            self._records = []
            self._save()

    def export(self) -> str:
        path = os.path.join(app_dir(), "proxy-records-export.json")
        with self._mu:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([dataclasses.asdict(r) for r in self._records], f, ensure_ascii=False, indent=2)
        return path
