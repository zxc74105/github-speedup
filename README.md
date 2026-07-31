# GitHub Multi-Proxy Downloader

Python + PySide6 桌面 GUI，通过智能测速和切换多个反向代理加速 GitHub 文件下载。

## 功能

- 多代理并行测速（vipertls Chrome TLS 指纹 + 30 线程池）
- 两阶段测速：连通性检测（34B）→ 体速测试（200KB）
- 下载组件（aria2 / Python 分片）**直连镜像代理网址**，不经本地代理
- Python 多代理并行分片下载（Range 分片 + 多代理并发 + 实时进度）
- aria2 多源并行下载（兜底） + 自动容错回退
- HTTP 加速代理服务（端口 9090，供浏览器/curl/aria2/脚本等**外部工具**使用）
- 代理使用记录统计与排序
- 实时下载进度、速度显示
- 独立 .exe，无需 Python 运行时

## 系统要求

- **OS**: Windows 7+
- **运行时**: 无（独立 .exe）

## 技术栈

- **语言**: Python 3.12+
- **GUI**: PySide6 (Qt6)
- **HTTP**: requests + vipertls
- **下载引擎**: Python 多线程分片 + aria2 (JSON-RPC)
- **打包**: PyInstaller (单 .exe)

## 构建

```bash
pip install -r requirements.txt
pyinstaller build.spec
```

输出在 `dist/github-speedup.exe`。

## 开发

```bash
python main.py
```

## License

MIT