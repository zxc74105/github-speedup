import os
import threading
from datetime import datetime


class AccessLogger:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, file_path: str):
        self._file_path = file_path
        self._mu = threading.Lock()
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "a", encoding="utf-8"):
            pass

    def log(self, fmt: str, *args):
        msg = fmt % args if args else fmt
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {msg}\n"
        with self._mu:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(line)

    @classmethod
    def init(cls, file_path: str):
        with cls._lock:
            cls._instance = cls(file_path)
        return cls._instance

    @classmethod
    def get(cls):
        return cls._instance
