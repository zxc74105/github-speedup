# v2.2.0 版本说明（2026-07-31）

## 核心变更：下载组件直连镜像代理
- **架构澄清**：9090 HTTP 加速代理只给外部工具（浏览器/curl/aria2/脚本）用，软件自身下载组件不再经过本地代理。
- **aria2 直连镜像**：`build_mirror_urls` 去掉 `http://127.0.0.1:6801/` 本地代理前缀，直接连接 `https://镜像域名/...`。
- **移除 viper 代理依赖**：删除下载组件对本地 viper 代理（6801）的启动/停止逻辑。

## 新增：legacy 多代理并行分片下载（主路径）

- 代理按测速结果排序（快的在前）。
- 后台探测文件真实大小（Range 0-0 + identity → Content-Range，实测 9.5s→4.4s）。
- 预分配文件 → 按 `max(4MB, total/8)` 分片 → 每片独立线程直连镜像（`Range: bytes=X-Y`）并行下载。
- 分片失败自动换下一个代理重试。
- 0.5s 实时上报进度（confirmed_bytes 累加）。

## 修复

- **大文件进度条 0%→100% 跳变**：根因是 aria2 走本地 viper 代理全量缓冲无进度；改并行分片直连后，137MB 安装包 15s 内下载 16MB 且进度持续增长，18MB 文件 11.3s 完成、全程有中间进度。
- **GUI 任务"大小"列恒为 0 B**：`_on_progress` 字段名 `total_bytes` → `totalBytes`。
- **被动加速 gzip 导致 Range/大小错乱**：`proxy_server.py` 请求显式加 `Accept-Encoding: identity`。
- **下载页新增事件日志面板**：实时显示开始/完成/失败/删除记录。

## 测试结果

- yt-dlp 18MB：completed，11.3s，total=18023276，26 个进度事件，中间值逐步增长。
- AI-SSH-Assistant 137MB：探测到 143654078 字节，15s 已下载 16MB，进度持续增长。
- aria2 直连镜像实测 TLS 不兼容（0B/0B 卡死），仅保留为兜底，不能作为主路径。

## 详细记录

- 修改记录：`docs/修改记录/MODIFY_aria2直连_并行分片_20260731.md`
- 错误记录：`错误修改记录.txt`【错误9】
- 架构视图已同步更新：docs/01、02、04、05、06、07、09、12、13、17、21、目录索引

## 下载（本 Release 附带 6 个二进制）

| 平台 | 文件 | 适用 |
| --- | --- | --- |
| Windows 64 位 | `github-speedup-x86_64.exe` | 常规 64 位 Windows 电脑 |
| Windows ARM64 | `github-speedup-arm64.exe` | 骁龙/ARM 芯片的 Windows 本 |
| Linux 64 位 | `github-speedup-x86_64` | 主流 64 位 Linux 服务器 |
| Linux ARM64 | `github-speedup-arm64` | 树莓派/ARM 云服务器 |
| macOS Intel | `github-speedup-darwin-x86_64` | 旧款 Intel Mac |
| macOS Apple Silicon | `github-speedup-darwin-arm64` | M1/M2/M3/M4 芯片 Mac |

> **说明**：32 位（x86）Windows 与 32 位 Linux 无法提供。原因：本项目基于 PySide6/Qt6，Qt6 已停止发布 32 位（win32 / i686）软件包，不存在对应 PyInstaller 构建环境。如确需 32 位，需要将 GUI 栈替换为 Tkinter 等仍支持 32 位的方案，另行发布。
> 构建方式：GitHub Actions（`.github/workflows/release.yml`）在打 tag 时自动构建并上传到 Releases。每个平台在对应架构的官方托管 runner 上原生构建（Windows x64/ARM64、Linux x64/ARM64、macOS Intel/Apple Silicon 各自独立编译），确保二进制与目标架构完全匹配。
