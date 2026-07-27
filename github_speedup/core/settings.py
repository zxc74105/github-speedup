import os
import json
import dataclasses
from typing import Optional
from .utils import app_dir


@dataclasses.dataclass
class Settings:
    defaultSaveDir: str = ""
    defaultConcurrency: int = 20
    partSize: int = 10
    maxRetry: int = 3
    timeout: int = 30
    autoTestOnStart: bool = True
    silentSpeedThreshold: float = 1.0
    silentLatencyThreshold: int = 500
    tcpTimeout: int = 5
    testFileSize: str = "1 MB"
    theme: str = "light"
    language: str = "zh-CN"
    checkUpdate: bool = True
    enableHTTPAPI: bool = True
    httpAPIPort: int = 9090
    allowRemoteAccess: bool = True


class SettingsManager:
    def __init__(self):
        self._path = os.path.join(app_dir(), "settings.json")

    def get_defaults(self) -> Settings:
        s = Settings()
        home = os.path.expanduser("~")
        s.defaultSaveDir = os.path.join(home, "Downloads")
        return s

    def load(self) -> Settings:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            defaults = self.get_defaults()
            for field in dataclasses.fields(defaults):
                if field.name in data:
                    setattr(defaults, field.name, data[field.name])
            return defaults
        except (FileNotFoundError, json.JSONDecodeError):
            return self.get_defaults()

    def save(self, settings: Settings):
        data = dataclasses.asdict(settings)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def reset(self) -> Settings:
        s = self.get_defaults()
        self.save(s)
        return s
