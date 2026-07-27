from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QStackedWidget, QLabel, QFrame,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

from .download_page import DownloadPage
from .proxy_page import ProxyPage
from .settings_page import SettingsPage
from ..core.proxy_manager import ProxyManager
from ..core.records import RecordsManager
from ..core.settings import SettingsManager
from ..server.proxy_server import ProxyServer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitHub Multi-Proxy Downloader")
        self.setMinimumSize(1800, 1000)
        self.resize(1800, 1000)

        self.proxy_mgr = ProxyManager()
        self.records_mgr = RecordsManager()
        self.settings_mgr = SettingsManager()
        self.server = ProxyServer(self.proxy_mgr, self.records_mgr)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(180)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        logo = QLabel("  Multi-Proxy DL")
        logo.setObjectName("logo")
        logo.setFixedHeight(48)
        logo.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        sidebar_layout.addWidget(logo)

        self.nav_btns = {}
        nav_items = [
            ("download", "⬇  下载管理"),
            ("proxies", "🌐  代理管理"),
            ("settings", "⚙  设置"),
        ]
        for key, text in nav_items:
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            sidebar_layout.addWidget(btn)
            self.nav_btns[key] = btn

        sidebar_layout.addStretch()

        self.silent_label = QLabel()
        self.silent_label.setObjectName("silentLabel")
        self.silent_label.setFixedHeight(28)
        self.silent_label.hide()
        sidebar_layout.addWidget(self.silent_label)

        self.content_stack = QStackedWidget()

        self.download_page = DownloadPage(self.records_mgr, self.proxy_mgr, self.settings_mgr)
        self.proxy_page = ProxyPage(self.proxy_mgr, self.records_mgr)
        self.settings_page = SettingsPage(self.settings_mgr, self.server, self.proxy_mgr, self.records_mgr)

        self.content_stack.addWidget(self.download_page)
        self.content_stack.addWidget(self.proxy_page)
        self.content_stack.addWidget(self.settings_page)

        root.addWidget(sidebar)
        root.addWidget(self.content_stack, 1)

        self._apply_style()
        self._switch_page("download")

    def _switch_page(self, key: str):
        for k, btn in self.nav_btns.items():
            btn.setChecked(k == key)
        idx = {"download": 0, "proxies": 1, "settings": 2}
        self.content_stack.setCurrentIndex(idx.get(key, 0))

    def update_silent_count(self, count: int):
        if count > 0:
            self.silent_label.setText(f"  静默: {count} 个代理")
            self.silent_label.show()
        else:
            self.silent_label.hide()

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #f5f6f8; }
            #sidebar {
                background: #f5f6f8;
                border-right: 1px solid #e0e0e0;
            }
            #logo {
                padding: 10px 16px;
                color: #1a1a2e;
                border-bottom: 1px solid #e8e8e8;
            }
            #navBtn {
                text-align: left;
                padding: 8px 16px;
                border: none;
                background: transparent;
                color: #333;
                font-size: 13px;
                border-radius: 0;
            }
            #navBtn:hover {
                background: #e8eaf0;
            }
            #navBtn:checked {
                background: #e0e4ff;
                color: #155DFC;
                font-weight: 600;
                border-left: 3px solid #155DFC;
            }
            #silentLabel {
                padding: 4px 16px;
                font-size: 11px;
                color: #e53935;
                background: #fce4ec;
            }
        """)
