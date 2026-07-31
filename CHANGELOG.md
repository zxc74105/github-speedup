### v2.2.0 (2026-07-31)

- 下载组件直连镜像代理网址（aria2 与 Python 分片均不再经过本地 127.0.0.1:9090/6801 代理）
- legacy 下载改为多代理并行分片：代理按速度排序 + Range 分片 + 每片独立线程，失败自动换代理重试，实时进度
- 移除 aria2 对本地 viper 代理（6801）的依赖：`build_mirror_urls` 直连 `scheme://domain/url`
- 移除 viper 代理的启动/停止逻辑（下载组件不再使用本地代理）
- 修复 GUI 大小列显示 0 B（`_on_progress` 字段名 `total_bytes` → `totalBytes`）
- `proxy_server.py` 被动加速请求显式加 `Accept-Encoding: identity`
- 大小探测提速：按速度排序取前 40、2048B 提前 break、3s 探测超时（9.5s → 4.4s）
- 大文件（如 137MB 安装包）进度条不再 0% 直接跳 100%，全程有中间进度

### v2.1.0 (2026-07-30)

- 移除内层 ThreadPoolExecutor，vipertls 直接在当前线程复用缓存客户端
- local_viper_proxy 改为流式转发（`stream=True` + `iter_content`）
- legacy 分片下载改为工作队列 + 动态代理轮询
- 修复 aria2 路径不记录代理成功记录的问题
- 修复下载进度不显示的问题（_on_progress 守卫 + 流式转发）
- 修复 _legacy_download 失败分片静默跳过的问题
- local_viper_proxy 使用线程本地客户端（`get_viper()` 替代全局 `VIPER`）

### v2.0.1 (2026-07-28)

- 代理测速改为两阶段：vipertls 连通性 → SHARED_SESSION 体速
- 线程池从 20 提升到 30
- 简化代理状态为"可用/不可用"两种
- 代理测速结果实时写入 GUI（每代理完成后立即刷新）
- 浏览器头提取为模块级常量 `BROWSER_HEADERS`

### v2.0.0

- Complete rewrite from Go + Wails v2 to Python + PySide6 + PyInstaller.
- Removed WebView2 dependency.
- Standalone single .exe with no runtime requirements.

### v1.1.0

- Added inactivity timeout for downloads (default 20s) to prevent hanging on slow proxies.
- Added `--timeout` flag to configure the inactivity period.
- Added debug logging for proxy switching events.
- Integrated speed and ETA metrics into the `--verbose` logging mode.
- Improved `--json-output` flag to automatically enable `--verbose` mode.
- Improved `--json-output` to report full progress statistics every 5 seconds.

### v1.0.0

- Initial release.