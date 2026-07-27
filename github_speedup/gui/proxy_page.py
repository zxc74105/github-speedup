import threading
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QLabel, QFrame,
    QMessageBox, QProgressBar, QFileDialog,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QBrush

from ..core.proxy_manager import ProxyManager, parse_speed_mbps, parse_latency_ms
from ..core.records import RecordsManager


class ProxyPage(QWidget):
    def __init__(self, proxy_mgr: ProxyManager, records_mgr: RecordsManager):
        super().__init__()
        self._proxy_mgr = proxy_mgr
        self._records_mgr = records_mgr
        self._search_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        toolbar = QFrame()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_test_all = QPushButton("全部测速")
        self.btn_test_all.setObjectName("primaryBtn")
        self.btn_test_all.clicked.connect(self._test_all)
        tb_layout.addWidget(self.btn_test_all)

        self.btn_preflight = QPushButton("代理预检")
        self.btn_preflight.clicked.connect(self._preflight)
        tb_layout.addWidget(self.btn_preflight)

        self.btn_import = QPushButton("导入")
        self.btn_import.clicked.connect(self._import_proxies)
        tb_layout.addWidget(self.btn_import)

        self.btn_export = QPushButton("导出")
        self.btn_export.clicked.connect(self._export_proxies)
        tb_layout.addWidget(self.btn_export)

        self.btn_delete = QPushButton("删除选中")
        self.btn_delete.setObjectName("dangerBtn")
        self.btn_delete.clicked.connect(self._delete_selected)
        tb_layout.addWidget(self.btn_delete)

        tb_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索域名...")
        self.search_input.setMaximumWidth(200)
        self.search_input.textChanged.connect(self._on_search)
        tb_layout.addWidget(self.search_input)

        layout.addWidget(toolbar)

        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(5)
        self.proxy_table.setHorizontalHeaderLabels(["域名", "当前状态", "延迟", "速度", "协议"])
        self.proxy_table.horizontalHeader().setStretchLastSection(False)
        self.proxy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.proxy_table.setColumnWidth(1, 100)
        self.proxy_table.setColumnWidth(2, 90)
        self.proxy_table.setColumnWidth(3, 120)
        self.proxy_table.setColumnWidth(4, 70)
        self.proxy_table.verticalHeader().hide()
        self.proxy_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.proxy_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.proxy_table.setAlternatingRowColors(True)
        layout.addWidget(self.proxy_table, 3)

        records_header = QFrame()
        rh_layout = QHBoxLayout(records_header)
        rh_layout.setContentsMargins(0, 0, 0, 0)
        rh = QLabel("🏆 成功代理记录")
        rh.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        rh_layout.addWidget(rh)
        rh_sub = QLabel("按成功下载次数排序，使用越多越靠前")
        rh_sub.setStyleSheet("color: #999; font-size: 11px;")
        rh_layout.addWidget(rh_sub)
        rh_layout.addStretch()
        layout.addWidget(records_header)

        self.record_table = QTableWidget()
        self.record_table.setColumnCount(5)
        self.record_table.setHorizontalHeaderLabels(["排名", "域名", "成功次数", "总大小", "最近使用"])
        self.record_table.horizontalHeader().setStretchLastSection(False)
        self.record_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.record_table.setColumnWidth(0, 60)
        self.record_table.setColumnWidth(2, 200)
        self.record_table.setColumnWidth(3, 100)
        self.record_table.setColumnWidth(4, 150)
        self.record_table.verticalHeader().hide()
        self.record_table.setAlternatingRowColors(True)
        self.record_table.setSelectionMode(QTableWidget.NoSelection)
        layout.addWidget(self.record_table, 2)

        self._apply_style()
        self._refresh()
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_records)
        self._refresh_timer.start(5000)

    def _apply_style(self):
        self.setStyleSheet("""
            #primaryBtn {
                background: #155DFC; color: white; border: none;
                padding: 6px 16px; border-radius: 4px; font-size: 13px;
            }
            #primaryBtn:hover { background: #0d4ad9; }
            #primaryBtn:disabled { background: #ccc; }
            #dangerBtn {
                background: white; color: #ff4d4f; border: 1px solid #ff4d4f;
                padding: 6px 16px; border-radius: 4px; font-size: 13px;
            }
            #dangerBtn:hover { background: #fff2f0; }
            QPushButton {
                border: 1px solid #d9d9d9; background: white;
                padding: 6px 16px; border-radius: 4px; font-size: 13px;
            }
            QPushButton:hover { border-color: #155DFC; color: #155DFC; }
            QTableWidget {
                border: 1px solid #e8e8e8; font-size: 12px;
                gridline-color: #f0f0f0;
            }
            QTableWidget::item { padding: 4px 8px; }
            QHeaderView::section {
                background: #fafbfc; border: none;
                border-bottom: 1px solid #e8e8e8;
                padding: 6px 8px; font-weight: 600; font-size: 12px;
            }
        """)

    def _on_search(self, text: str):
        self._search_text = text
        self._refresh_proxies()

    def _filtered_proxies(self):
        proxies = self._proxy_mgr.get_all()
        if self._search_text:
            proxies = [p for p in proxies if self._search_text.lower() in p.domain.lower()]
        return proxies

    def _refresh(self):
        self._refresh_proxies()
        self._refresh_records()

    def _refresh_proxies(self):
        proxies = self._filtered_proxies()
        self.proxy_table.setRowCount(len(proxies))
        for i, p in enumerate(proxies):
            dot_color = {
                "active": "#00c853", "silent": "#ffb300",
                "offline": "#ff1744", "checking": "#90caf9",
            }.get(p.status, "#90caf9")

            domain_widget = QWidget()
            dl = QHBoxLayout(domain_widget)
            dl.setContentsMargins(4, 0, 4, 0)
            dot = QLabel(f"● ")
            dot.setStyleSheet(f"color: {dot_color}; font-size: 14px;")
            dl.addWidget(dot)
            dl.addWidget(QLabel(p.domain))
            dl.addStretch()
            self.proxy_table.setCellWidget(i, 0, domain_widget)

            status_colors = {
                "active": "green", "silent": "orange",
                "offline": "red", "checking": "blue",
            }
            status_texts = {
                "active": "可用", "silent": "静默",
                "offline": "离线", "checking": "检测中",
            }
            st = QTableWidgetItem(status_texts.get(p.status, p.status))
            st.setForeground(QBrush(QColor(status_colors.get(p.status, "#999"))))
            self.proxy_table.setItem(i, 1, st)

            lat = QTableWidgetItem(p.latency or "-")
            lat.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.proxy_table.setItem(i, 2, lat)

            spd = QTableWidgetItem(p.speed or "-")
            spd.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.proxy_table.setItem(i, 3, spd)

            scheme = QTableWidgetItem(p.scheme or "?")
            scheme.setTextAlignment(Qt.AlignCenter)
            self.proxy_table.setItem(i, 4, scheme)

    def _refresh_records(self):
        records = self._records_mgr.get_all()
        self.record_table.setRowCount(len(records))
        for i, r in enumerate(records):
            rank = QTableWidgetItem(f"#{i + 1}")
            rank.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            rank.setForeground(QBrush(QColor("#f9a825" if i < 3 else "#888")))
            rank.setTextAlignment(Qt.AlignCenter)
            self.record_table.setItem(i, 0, rank)

            self.record_table.setItem(i, 1, QTableWidgetItem(r.domain))

            count_widget = QWidget()
            cl = QHBoxLayout(count_widget)
            cl.setContentsMargins(4, 2, 4, 2)
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setValue(min(100, int((r.successCount / 50) * 100)))
            pb.setFixedWidth(80)
            pb.setFixedHeight(14)
            pb.setTextVisible(False)
            cl.addWidget(pb)
            cl.addWidget(QLabel(f"{r.successCount} 次"))
            cl.addStretch()
            self.record_table.setCellWidget(i, 2, count_widget)

            total = QTableWidgetItem(
                f"{r.totalBytes / (1024 * 1024):.1f} MB" if r.totalBytes else "-"
            )
            total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.record_table.setItem(i, 3, total)

            last_used = r.lastUsedAt
            if last_used:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(last_used)
                    last_used = dt.strftime("%m-%d %H:%M")
                except Exception:
                    pass
            else:
                last_used = "从未"
            self.record_table.setItem(i, 4, QTableWidgetItem(last_used))

    def _test_all(self):
        self.btn_test_all.setEnabled(False)
        self.btn_test_all.setText("测速中...")

        def run():
            self._proxy_mgr.test_all()
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self.btn_test_all, "setEnabled", Qt.QueuedConnection, Q_ARG(bool, True)
            )
            QMetaObject.invokeMethod(
                self.btn_test_all, "setText", Qt.QueuedConnection, Q_ARG(str, "全部测速")
            )
            QMetaObject.invokeMethod(self, "_refresh_proxies", Qt.QueuedConnection)

        threading.Thread(target=run, daemon=True).start()

    def _preflight(self):
        def run():
            result = self._proxy_mgr.preflight_check()
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            msg = f"预检完成: {result.available} 可用, {result.silent} 静默"
            QMetaObject.invokeMethod(
                self, "_show_message", Qt.QueuedConnection, Q_ARG(str, msg)
            )
            QMetaObject.invokeMethod(self, "_refresh_proxies", Qt.QueuedConnection)
            parent = self.parent()
            while parent and not hasattr(parent, "update_silent_count"):
                parent = parent.parent()
            if parent and hasattr(parent, "update_silent_count"):
                QMetaObject.invokeMethod(
                    parent, "update_silent_count", Qt.QueuedConnection,
                    Q_ARG(int, result.silent),
                )

        threading.Thread(target=run, daemon=True).start()

    def _import_proxies(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择代理文件", "",
            "Text files (*.txt *.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            count = self._proxy_mgr.import_from_file(path)
            QMessageBox.information(self, "导入完成", f"成功导入 {count} 个代理")
            self._refresh_proxies()
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _export_proxies(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出代理", "proxies-export.txt",
            "Text files (*.txt);;All files (*.*)",
        )
        if not path:
            return
        try:
            self._proxy_mgr.export_to_file(path)
            QMessageBox.information(self, "导出完成", f"已导出到 {path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _delete_selected(self):
        rows = self.proxy_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "提示", "请选择要删除的代理")
            return
        proxies = self._filtered_proxies()
        domains = []
        for row in rows:
            if row.row() < len(proxies):
                domains.append(proxies[row.row()].domain)
        if not domains:
            return
        confirm = QMessageBox.question(
            self, "确认删除",
            f"将删除 {len(domains)} 个代理及其成功记录?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._proxy_mgr.delete_domains(domains)
        self._records_mgr.delete_domains(domains)
        self._refresh()

    def _show_message(self, msg: str):
        QMessageBox.information(self, "完成", msg)
