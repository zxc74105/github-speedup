# README

## About

GitHub Multi-Proxy Downloader — Python + PySide6 standalone desktop GUI.

A desktop application that accelerates GitHub asset downloads by intelligently testing and switching between multiple reverse proxies. Built as a standalone Windows executable with no runtime dependencies.

## Features

- Multi-proxy parallel speed testing
- Automatic failover to the fastest proxy
- Concurrent downloads via ThreadPoolExecutor
- Standalone .exe — no Python or WebView2 required
- Real-time speed and ETA metrics
- Configurable download timeout

## System Requirements

- **OS**: Windows 7+
- **Runtime**: None (standalone .exe, Python not required)

## Tech Stack

- **Language**: Python 3.12+
- **GUI**: PySide6 (Qt6)
- **HTTP**: requests
- **Concurrency**: ThreadPoolExecutor
- **Packaging**: PyInstaller (single .exe)

## Building

### Prerequisites

- Python 3.12+
- pip install -r requirements.txt

### Compile standalone executable

```bash
pyinstaller --onefile --windowed --name "github-speedup" main.py
```

The output will be in the `dist/` directory as a single `.exe` file.

## Development

Run from source without building:

```bash
python main.py
```

## Screenshots

![screenshot](screenshot.png)

## License

MIT