import os
import threading
import time
import dataclasses
from typing import Optional
from urllib.parse import urlparse

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QLineEdit, QSpinBox,
    QLabel, QFormLayout, QDialogButtonBox, QTabWidget, QFrame,
    QProgressBar, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, Signal, QObject, QThread, QTimer
from PySide6.QtGui import QFont, QColor, QBrush

from ..core.downloader import (
    DownloadTask, ProgressData, start_background_download,
    cancel_download, guess_file_name,
)
from ..core.records import RecordsManager, TaskInfo
from ..core.proxy_manager import ProxyManager
from ..core.settings import SettingsManager
from ..core.utils import app_dir


class ProgressSignals(QObject):
    progress = Signal(ProgressData)


class NewTaskDialog(QDialog):
    def __init__(self, settings_mgr: SettingsManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建下载任务")
        self.setMinimumWidth(420)
        settings = settings_mgr.load()

        layout = QFormLayout(self)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://github.com/...")
        layout.addRow("下载链接", self.url_input)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 50)
        self.concurrency_spin.setValue(settings.defaultConcurrency)
        layout.addRow("并发数", self.concurrency_spin)

        self.part_size_spin = QSpinBox()
        self.part_size_spin.setRange(5, 50)
        self.part_size_spin.setValue(settings.partSize)
        layout.addRow("分片大小 (MB)", self.part_size_spin)

        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(settings.maxRetry)
        layout.addRow("最大重试", self.retry_spin)

        self.save_dir_input = QLineEdit(settings.defaultSaveDir)
        layout.addRow("保存目录", self.save_dir_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self) -> dict:
        return {
            "url": self.url_input.text().strip(),
            "save_dir": self.save_dir_input.text().strip(),
            "concurrency": self.concurrency_spin.value(),
            "part_size": self.part_size_spin.value(),
            "max_retry": self.retry_spin.value(),
        }


class DownloadPage(QWidget):
    def __init__(self, records_mgr: RecordsManager, proxy_mgr: ProxyManager,
                 settings_mgr: SettingsManager):
        super().__init__()
        self._records_mgr = records_mgr
        self._proxy_mgr = proxy_mgr
        self._settings_mgr = settings_mgr

        self._tasks: list[TaskInfo] = []
        self._task_threads: dict[int, threading.Thread] = {}
        self._signals: dict[int, ProgressSignals] = {}
        self._filter = "all"
        self._next_id = 1
        self._selected_task_id: Optional[int] = None

        self._load_tasks()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 8, 12, 8)

        self.btn_new = QPushButton("+ 新建任务")
        self.btn_new.setObjectName("actionBtn")
        self.btn_new.clicked.connect(self._new_task)
        tb_layout.addWidget(self.btn_new)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self._cancel_selected)
        tb_layout.addWidget(self.btn_cancel)

        self.btn_delete = QPushButton("删除选中")
        self.btn_delete.clicked.connect(self._delete_selected)
        tb_layout.addWidget(self.btn_delete)

        tb_layout.addStretch()

        self.filter_btns = {}
        for key, text in [("all", "全部"), ("downloading", "下载中"),
                          ("completed", "已完成"), ("failed", "失败")]:
            btn = QPushButton(text)
            btn.setObjectName("filterBtn")
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda checked, k=key: self._set_filter(k))
            tb_layout.addWidget(btn)
            self.filter_btns[key] = btn

        layout.addWidget(toolbar)

        header = ["文件名", "大小", "进度", "速度", "状态"]
        self.table = QTableWidget()
        self.table.setColumnCount(len(header))
        self.table.setHorizontalHeaderLabels(header)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 90)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(76)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        self.detail_tabs = QTabWidget()
        self.detail_tabs.setMaximumHeight(200)
        self.detail_tabs.setVisible(False)

        self.detail_label = QLabel("选择一个任务查看详情")
        self.detail_tabs.addTab(self.detail_label, "详情")

        self.detail_worker = QLabel("Worker 实时状态")
        self.detail_tabs.addTab(self.detail_worker, "Worker")

        self.detail_log = QLabel("事件日志")
        self.detail_tabs.addTab(self.detail_log, "日志")

        layout.addWidget(self.detail_tabs)

        self._apply_style()
        self._refresh_table()
        self._start_progress_timer()

    def _apply_style(self):
        self.setStyleSheet("""
            #toolbar {
                background: #fafbfc;
                border-bottom: 1px solid #f0f0f0;
            }
            #actionBtn {
                background: #155DFC;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            #actionBtn:hover { background: #0d4ad9; }
            #filterBtn {
                border: 1px solid #d9d9d9;
                background: white;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            #filterBtn:checked {
                background: #155DFC;
                color: white;
                border-color: #155DFC;
            }
            QTableWidget {
                border: none;
                font-size: 12px;
                gridline-color: #f0f0f0;
            }
            QTableWidget::item { padding: 4px 8px; }
            QTableWidget::item:selected { background: #e6f0ff; color: black; }
            QHeaderView::section {
                background: #fafbfc;
                border: none;
                border-bottom: 1px solid #e8e8e8;
                padding: 6px 8px;
                font-weight: 600;
                font-size: 12px;
            }
        """)

    def _load_tasks(self):
        path = os.path.join(app_dir(), "tasks.json")
        import json
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._tasks = []
                valid_fields = {f.name for f in dataclasses.fields(TaskInfo)}
                for entry in data:
                    filtered = {k: v for k, v in entry.items() if k in valid_fields}
                    t = TaskInfo(**filtered)
                    if t.id >= self._next_id:
                        self._next_id = t.id + 1
                    if t.status in ("downloading", "preparing"):
                        t.status = "paused"
                    self._tasks.append(t)
        except (FileNotFoundError, json.JSONDecodeError):
            self._tasks = []

    def _save_tasks(self):
        path = os.path.join(app_dir(), "tasks.json")
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                [dataclasses.asdict(t) for t in self._tasks],
                f, ensure_ascii=False, indent=2,
            )

    def _start_progress_timer(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh_table)
        self._timer.start(500)

    def _set_filter(self, key: str):
        self._filter = key
        for k, btn in self.filter_btns.items():
            btn.setChecked(k == key)
        self._refresh_table()

    def _get_filtered_tasks(self):
        if self._filter == "all":
            return self._tasks
        if self._filter == "downloading":
            return [t for t in self._tasks if t.status in ("downloading", "preparing")]
        if self._filter == "completed":
            return [t for t in self._tasks if t.status == "completed"]
        if self._filter == "failed":
            return [t for t in self._tasks if t.status in ("failed", "paused")]
        return self._tasks

    def _on_selection_changed(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            idx = rows[0].row()
            items = self._get_filtered_tasks()
            if idx < len(items):
                self._selected_task_id = items[idx].id
                self.detail_tabs.setVisible(True)
                task = next((t for t in self._tasks if t.id == self._selected_task_id), None)
                if task:
                    self.detail_label.setText(
                        f"文件名: {task.fileName}\n"
                        f"大小: {self._format_bytes(task.totalBytes)}\n"
                        f"已下载: {self._format_bytes(task.downloaded)}\n"
                        f"速度: {self._format_speed(task.speed)}\n"
                        f"状态: {task.status}\n"
                        f"保存目录: {task.saveDir}"
                    )
                return
        self._selected_task_id = None
        self.detail_tabs.setVisible(False)

    def _new_task(self):
        dlg = NewTaskDialog(self._settings_mgr, self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data["url"]:
            QMessageBox.warning(self, "提示", "请输入下载链接")
            return

        task_id = self._next_id
        self._next_id += 1

        info = TaskInfo(
            id=task_id,
            url=data["url"],
            fileName=guess_file_name(data["url"]),
            saveDir=data["save_dir"],
            status="preparing",
            createdAt=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._tasks.append(info)
        self._save_tasks()
        self._start_download(task_id, data)

    def _start_download(self, task_id: int, data: dict):
        task = DownloadTask(
            url=data["url"],
            save_dir=data["save_dir"],
            part_size_bytes=data["part_size"] * 1024 * 1024,
            max_concurrent=data["concurrency"],
            max_retry=data.get("max_retry", 3),
            timeout=30,
        )

        signals = ProgressSignals()
        self._signals[task_id] = signals

        def on_progress(pd: ProgressData):
            pd.task_id = task_id
            signals.progress.emit(pd)

        def record_success(domain: str, bs: int, spd: float):
            self._records_mgr.record_success(domain, bs, spd)

        def record_failure(domain: str):
            self._records_mgr.record_failure(domain)

        signals.progress.connect(lambda pd: self._on_progress(pd))

        def run():
            info = next((t for t in self._tasks if t.id == task_id), None)
            if not info:
                return
            info.status = "downloading"
            self._save_tasks()

            result = start_background_download(
                task, record_success, record_failure, on_progress, task_id,
            )
            if info.status != "failed":
                info.fileName = result.file_name
                info.totalBytes = result.total_bytes
                info.downloaded = result.downloaded
                info.speed = result.speed
                info.status = result.status
                if result.total_bytes > 0:
                    info.progress = (result.downloaded / result.total_bytes) * 100
                self._save_tasks()

        t = threading.Thread(target=run, daemon=True)
        self._task_threads[task_id] = t
        t.start()

    def _on_progress(self, pd: ProgressData):
        info = next((t for t in self._tasks if t.id == pd.task_id), None)
        if not info:
            return
        if pd.downloaded is not None:
            info.downloaded = pd.downloaded
        if pd.total_bytes is not None:
            info.total_bytes = pd.total_bytes
        if pd.speed is not None:
            info.speed = pd.speed
        if pd.total_bytes and pd.total_bytes > 0:
            info.progress = (info.downloaded / info.total_bytes) * 100
        info.status = pd.status or "downloading"

    def _cancel_selected(self):
        if self._selected_task_id is None:
            QMessageBox.warning(self, "提示", "请先选择一个任务")
            return
        cancel_download(self._selected_task_id)
        task = next((t for t in self._tasks if t.id == self._selected_task_id), None)
        if task:
            task.status = "cancelled"
            self._save_tasks()
        self._refresh_table()

    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "提示", "请选择要删除的任务")
            return
        ids = []
        items = self._get_filtered_tasks()
        for row in rows:
            if row.row() < len(items):
                ids.append(items[row.row()].id)
        if not ids:
            return
        confirm = QMessageBox.question(
            self, "确认删除", f"将删除 {len(ids)} 个任务?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._tasks = [t for t in self._tasks if t.id not in ids]
        self._save_tasks()
        if self._selected_task_id in ids:
            self._selected_task_id = None
            self.detail_tabs.setVisible(False)
        self._refresh_table()

    def _refresh_table(self):
        items = self._get_filtered_tasks()
        self.table.setRowCount(len(items))
        for i, t in enumerate(items):
            name_widget = QWidget()
            nl = QVBoxLayout(name_widget)
            nl.setContentsMargins(4, 2, 4, 2)
            nl.setSpacing(0)

            fname = QLabel(t.fileName or "未知")
            fname.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
            nl.addWidget(fname)

            sdir = QLabel(t.saveDir or "")
            sdir.setStyleSheet("color: #999; font-size: 10px;")
            nl.addWidget(sdir)

            self.table.setCellWidget(i, 0, name_widget)

            size_item = QTableWidgetItem(self._format_bytes(t.totalBytes))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 1, size_item)

            prog_widget = QWidget()
            pl = QVBoxLayout(prog_widget)
            pl.setContentsMargins(4, 2, 4, 2)
            pl.setSpacing(0)
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setValue(int(t.progress))
            pb.setTextVisible(True)
            pb.setFixedHeight(18)
            pl.addWidget(pb)
            pl.addWidget(QLabel(
                f"{self._format_bytes(t.downloaded)} / {self._format_bytes(t.totalBytes)}",
                styleSheet="color: #888; font-size: 10px;",
            ))
            self.table.setCellWidget(i, 2, prog_widget)

            speed_item = QTableWidgetItem(self._format_speed(t.speed))
            speed_item.setForeground(QBrush(QColor("#155DFC")))
            speed_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, speed_item)

            status_colors = {
                "preparing": "#1890ff", "downloading": "#1890ff",
                "paused": "#faad14", "completed": "#52c41a",
                "failed": "#ff4d4f", "cancelled": "#999",
            }
            status_texts = {
                "preparing": "准备中", "downloading": "下载中",
                "paused": "已暂停", "completed": "已完成",
                "failed": "失败", "cancelled": "已取消",
            }
            status_item = QTableWidgetItem(status_texts.get(t.status, t.status))
            status_item.setForeground(QBrush(QColor(
                status_colors.get(t.status, "#999")
            )))
            self.table.setItem(i, 4, status_item)

    @staticmethod
    def _format_bytes(b: int) -> str:
        if b < 1024:
            return f"{b} B"
        if b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        if b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        return f"{b / (1024 * 1024 * 1024):.2f} GB"

    @staticmethod
    def _format_speed(speed: float) -> str:
        if speed <= 0:
            return "-"
        mbps = (speed * 8) / 1_000_000
        return f"{mbps:.1f} Mbps"
