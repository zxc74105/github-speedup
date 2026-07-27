# ALIGNMENT: Python + PySide6 重构

## 目标
将 Go + Wails v2 (WebView2) 项目完全重写为 Python + PySide6 + PyInstaller，消除 WebView2 依赖，实现零运行时环境的单文件 .exe。

## 范围
- 删除所有 Go 源代码、前端代码、Node.js 相关配置
- 保留现有文档目录（docs/），更新内容为新架构
- 保留 AGENTS.md（更新启动方法）
- 保留 .git / .github / LICENSE / opencode.json
- 其余全部替换为 Python 代码

## 数据文件兼容
- `proxies-active.json` / `proxies.json` / `tasks.json` / `proxy-records.json` / `settings.json` 格式不变
- `proxy-access.log` 格式不变

## 技术栈

| 层 | 选择 | 理由 |
|---|------|------|
| 语言 | Python 3.10+ | 兼容性最好，Win7+ 可用 |
| GUI | PySide6 (Qt6) | 稳定原生控件，发布时 dll 可内嵌 |
| 下载引擎 | `requests` + `ThreadPoolExecutor(20)` | GIL 在 I/O 时释放，多线程效率高 |
| 被动代理 | `http.server.ThreadingHTTPServer` | 轻量够用，不需三方 asyncio |
| 打包 | PyInstaller (--onefile) | 单 .exe 输出，~40-50MB |
| 图标 | 内嵌 base64 SVG | 零外部文件 |

## 核心模块

```
github-speedup/
├── main.py                         # PyInstaller 入口
├── requirements.txt                # PySide6, requests, pyinstaller
├── github_speedup/
│   ├── __init__.py
│   ├── core/
│   │   ├── downloader.py           # 多代理并行分片下载（ThreadPoolExecutor）
│   │   ├── proxy_manager.py        # 代理管理（测试/预检/导入导出）
│   │   ├── settings.py             # 设置管理
│   │   ├── utils.py                # 共享 Transport / 浏览器头 / 工具函数
│   │   └── logger.py               # 访问日志
│   ├── gui/
│   │   ├── main_window.py          # 主窗口（侧栏 + QStackedWidget）
│   │   ├── download_page.py        # 下载管理页
│   │   ├── proxy_page.py           # 代理管理页
│   │   └── settings_page.py        # 设置页
│   └── server/
│       ├── __init__.py
│       └── proxy_server.py         # HTTP 被动加速服务
```

## 质量门控
- 对应 Go 版本的所有 14 个测试场景必须全部通过
- GUI 三个页面功能完整可操作
- HTTP 被动代理服务 /health 返回 `{"status":"ok"}`
- PyInstaller --onefile 打包成功
