import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from github_speedup.gui.main_window import MainWindow
from github_speedup.core.logger import AccessLogger
from github_speedup.core.utils import app_dir


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("GitHub Multi-Proxy Downloader")
    app.setOrganizationName("github-speedup")

    log_path = os.path.join(app_dir(), "proxy-access.log")
    AccessLogger.init(log_path)

    window = MainWindow()
    window.show()

    settings = window.settings_mgr.load()
    if settings.autoTestOnStart:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, lambda: _run_preflight(window))

    window.server.start(settings.httpAPIPort, settings.allowRemoteAccess)

    from github_speedup.core.downloader import shutdown_backend
    app.aboutToQuit.connect(shutdown_backend)
    sys.exit(app.exec())


def _run_preflight(window):
    import threading

    def run():
        result = window.proxy_mgr.preflight_check()
        proxy_page = window.proxy_page
        proxy_page._preflight_finished.emit(
            f"预检完成: {result.available} 个可用",
            result.total - result.available,
        )

    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    main()
