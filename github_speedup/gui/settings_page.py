from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QCheckBox, QPushButton, QGroupBox, QLabel,
    QHBoxLayout, QMessageBox, QFileDialog, QDoubleSpinBox,
    QRadioButton, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ..core.settings import SettingsManager
from ..core.proxy_manager import ProxyManager
from ..core.records import RecordsManager
from ..server.proxy_server import ProxyServer


class SettingsPage(QWidget):
    def __init__(self, settings_mgr: SettingsManager, server: ProxyServer,
                 proxy_mgr: ProxyManager, records_mgr: RecordsManager):
        super().__init__()
        self._settings_mgr = settings_mgr
        self._server = server
        self._proxy_mgr = proxy_mgr
        self._records_mgr = records_mgr

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        title = QLabel("⚙ 设置")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        self._settings = self._settings_mgr.load()
        self._build_form(layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_reset = QPushButton("恢复默认")
        self.btn_reset.clicked.connect(self._reset)
        btn_layout.addWidget(self.btn_reset)
        self.btn_save = QPushButton("💾 保存设置")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.clicked.connect(self._save)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

        layout.addStretch()
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            QGroupBox {
                font-weight: 600; font-size: 13px;
                border: 1px solid #e8e8e8; border-radius: 6px;
                margin-top: 12px; padding: 16px 12px 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px; padding: 0 6px;
                background: white;
            }
            #saveBtn {
                background: #155DFC; color: white; border: none;
                padding: 8px 24px; border-radius: 4px; font-size: 13px;
            }
            #saveBtn:hover { background: #0d4ad9; }
            QPushButton {
                border: 1px solid #d9d9d9; background: white;
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
            }
            QPushButton:hover { border-color: #155DFC; color: #155DFC; }
            QLineEdit, QSpinBox, QComboBox, QDoubleSpinBox {
                padding: 4px 8px; border: 1px solid #d9d9d9;
                border-radius: 4px; font-size: 13px;
            }
        """)

    def _build_form(self, layout):
        s = self._settings

        dl_group = QGroupBox("⬇ 下载设置")
        dl_form = QFormLayout(dl_group)

        self.save_dir = QLineEdit(s.defaultSaveDir)
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.save_dir, 1)
        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(btn_browse)
        dl_form.addRow("默认下载文件夹", dir_layout)

        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 50)
        self.concurrency.setValue(s.defaultConcurrency)
        dl_form.addRow("默认并发数", self.concurrency)

        self.part_size = QComboBox()
        for val in [5, 10, 20, 50]:
            self.part_size.addItem(f"{val} MB", val)
        self.part_size.setCurrentIndex(self.part_size.findData(s.partSize))
        dl_form.addRow("分片大小", self.part_size)

        self.max_retry = QComboBox()
        for val in [0, 1, 2, 3, 5, 10]:
            label = "不重试" if val == 0 else f"{val} 次"
            self.max_retry.addItem(label, val)
        self.max_retry.setCurrentIndex(self.max_retry.findData(s.maxRetry))
        dl_form.addRow("最大重试次数", self.max_retry)

        self.timeout = QComboBox()
        for val in [10, 20, 30, 60, 120]:
            self.timeout.addItem(f"{val} 秒", val)
        self.timeout.setCurrentIndex(self.timeout.findData(s.timeout))
        dl_form.addRow("请求超时", self.timeout)

        layout.addWidget(dl_group)

        px_group = QGroupBox("🌐 代理设置")
        px_form = QFormLayout(px_group)

        self.auto_test = QCheckBox("启动时自动测速")
        self.auto_test.setChecked(s.autoTestOnStart)
        px_form.addRow("", self.auto_test)

        self.speed_threshold = QDoubleSpinBox()
        self.speed_threshold.setRange(0.5, 50)
        self.speed_threshold.setSingleStep(0.5)
        self.speed_threshold.setValue(s.silentSpeedThreshold)
        px_form.addRow("静默速度阈值 (Mbps)", self.speed_threshold)

        self.latency_threshold = QSpinBox()
        self.latency_threshold.setRange(100, 2000)
        self.latency_threshold.setSingleStep(50)
        self.latency_threshold.setValue(s.silentLatencyThreshold)
        px_form.addRow("静默延迟阈值 (ms)", self.latency_threshold)

        self.tcp_timeout = QComboBox()
        for val in [1, 3, 5, 10, 30]:
            self.tcp_timeout.addItem(f"{val} 秒", val)
        self.tcp_timeout.setCurrentIndex(self.tcp_timeout.findData(s.tcpTimeout))
        px_form.addRow("TCP 连接超时", self.tcp_timeout)

        layout.addWidget(px_group)

        sv_group = QGroupBox("🔌 HTTP API 加速服务")
        sv_form = QFormLayout(sv_group)

        status_label = QLabel("状态: ")
        self.server_status = QLabel("停止")
        self.server_status.setStyleSheet("color: #999;")
        sv_form.addRow(status_label, self.server_status)
        self._refresh_server_status()

        self.srv_port = QSpinBox()
        self.srv_port.setRange(1024, 65535)
        self.srv_port.setValue(s.httpAPIPort)
        sv_form.addRow("监听端口", self.srv_port)

        self.allow_remote = QCheckBox("允许远程访问")
        self.allow_remote.setChecked(s.allowRemoteAccess)
        sv_form.addRow("", self.allow_remote)

        usage = QLabel(
            f'<span style="color:#666;font-size:12px;">'
            f'用法: <code>http://127.0.0.1:{s.httpAPIPort}/'
            f'https://github.com/.../file.zip</code></span>'
        )
        usage.setTextFormat(Qt.RichText)
        sv_form.addRow("", usage)

        layout.addWidget(sv_group)

        data_group = QGroupBox("🗄 数据管理")
        data_form = QFormLayout(data_group)
        data_btns = QHBoxLayout()

        btn_export = QPushButton("📤 导出记录")
        btn_export.clicked.connect(self._export_records)
        data_btns.addWidget(btn_export)

        btn_clear = QPushButton("🗑 清除所有记录")
        btn_clear.setObjectName("dangerBtn")
        btn_clear.clicked.connect(self._clear_records)
        data_btns.addWidget(btn_clear)

        data_form.addRow("", data_btns)
        layout.addWidget(data_group)

    def _browse_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择下载目录", self.save_dir.text())
        if dir_path:
            self.save_dir.setText(dir_path)

    def _refresh_server_status(self):
        if self._server.is_running:
            self.server_status.setText("● 运行中")
            self.server_status.setStyleSheet("color: #52c41a; font-weight: 600;")
        else:
            self.server_status.setText("停止")
            self.server_status.setStyleSheet("color: #999;")

    def _save(self):
        from ..core.settings import Settings
        s = Settings(
            defaultSaveDir=self.save_dir.text(),
            defaultConcurrency=self.concurrency.value(),
            partSize=self.part_size.currentData(),
            maxRetry=self.max_retry.currentData(),
            timeout=self.timeout.currentData(),
            autoTestOnStart=self.auto_test.isChecked(),
            silentSpeedThreshold=self.speed_threshold.value(),
            silentLatencyThreshold=self.latency_threshold.value(),
            tcpTimeout=self.tcp_timeout.currentData(),
            testFileSize="1 MB",
            theme="light",
            language="zh-CN",
            checkUpdate=True,
            enableHTTPAPI=True,
            httpAPIPort=self.srv_port.value(),
            allowRemoteAccess=self.allow_remote.isChecked(),
        )
        self._settings_mgr.save(s)

        if self._server.is_running:
            self._server.stop()
        self._server.start(s.httpAPIPort, s.allowRemoteAccess)
        self._refresh_server_status()
        QMessageBox.information(self, "设置", "设置已保存")

    def _reset(self):
        confirm = QMessageBox.question(
            self, "确认", "恢复默认设置?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        s = self._settings_mgr.reset()
        self.save_dir.setText(s.defaultSaveDir)
        self.concurrency.setValue(s.defaultConcurrency)
        self.part_size.setCurrentIndex(self.part_size.findData(s.partSize))
        self.max_retry.setCurrentIndex(self.max_retry.findData(s.maxRetry))
        self.timeout.setCurrentIndex(self.timeout.findData(s.timeout))
        self.auto_test.setChecked(s.autoTestOnStart)
        self.speed_threshold.setValue(s.silentSpeedThreshold)
        self.latency_threshold.setValue(s.latency_threshold)
        self.tcp_timeout.setCurrentIndex(self.tcp_timeout.findData(s.tcpTimeout))
        self.srv_port.setValue(s.httpAPIPort)
        self.allow_remote.setChecked(s.allowRemoteAccess)
        QMessageBox.information(self, "设置", "已恢复默认设置")

    def _export_records(self):
        try:
            path = self._records_mgr.export()
            QMessageBox.information(self, "导出完成", f"已导出到 {path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _clear_records(self):
        confirm = QMessageBox.question(
            self, "确认清除", "确定清除所有成功代理记录? 此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._records_mgr.clear()
        QMessageBox.information(self, "完成", "已清除所有记录")
