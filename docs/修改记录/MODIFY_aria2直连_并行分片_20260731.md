# MODIFY 修改记录：aria2 直连镜像 + legacy 多代理并行分片下载

时间戳：2026-07-31

## 1. 修改目标
- 用户澄清架构：软件延伸出的 9090 代理（http_server / ProxyServer）是**给外部工具使用的**，不是给软件自身组件使用。
- 软件自身下载组件（GUI 下载、aria2）应**直接连接镜像代理网址**（`https://镜像域名/https://github.com/...`），不应经过本地 127.0.0.1:9090 或 127.0.0.1:6801 代理。
- 修复真实大文件（`AI-SSH-Assistant-1.8.23-setup-x64.exe`，143654078 字节）下载时进度条从 0% 直接跳到 100%、无中间进度的问题。

## 2. 当前代码状态
- `github_speedup/core/aria2_downloader.py` `build_mirror_urls`（第 130-145 行）：把每个镜像 URL 套上 `http://127.0.0.1:6801/` 本地 viper 代理前缀 —— **违反用户架构意图**（组件不应走本地代理）。
- `github_speedup/core/local_viper_proxy.py` 第 50 行 `body = resp.content`：viper 代理全量缓冲，aria2 无进度（这是"0%→100%"根因之一）。
- `github_speedup/core/downloader.py` `_legacy_download`：单流串行尝试代理，`per_proxy_timeout = min(task.timeout, 15)`，对大文件 15s 单流超时容易全部失败 → 落入 aria2 兜底（无进度）。
- 已修改（本次会话前半）：`download_page.py` 字段名 bug（`total_bytes`→`totalBytes`）、`get_file_size_via_proxies` 提速、后台探测线程、`download_via` 响应头 Content-Length 更新、`proxy_server.py` 加 `Accept-Encoding: identity`、`downloader.py` 顶部已加 `import re`。

## 3. 实测诊断数据
- 真实 URL：`https://github.com/aifuqiang02/ai-ssh-assistant/releases/download/v1.8.23/AI-SSH-Assistant-1.8.23-setup-x64.exe`
- 文件真实大小：143654078 字节（Content-Range: bytes 0-1023/143654078）
- 支持 206 Range 的镜像（前 6 快中）：gh.felicity.ac.cn / g.blfrp.cn / gh.sixyin.com / gh.ddlc.top 全部返回 206 + 正确 Content-Range；gh-proxy.net 返回 200 无 Content-Length；github.geekery.cn 连接错误。
- aria2 直连镜像（`--check-certificate=false` + 完整浏览器头 + split=4）实测：**0B/0B 完全卡死 60s+**（CN:1 连接建立但服务器不返回数据）→ aria2 自带 TLS 与镜像不兼容，直连不可靠。
- aria2 走 6801 viper 代理：能下载但全量缓冲无进度（旧根因）。
- Python requests（SHARED_SESSION，`Accept-Encoding: identity`）直连镜像：206 正常、有真实进度。

## 4. 计划修改方案
### 4.1 `aria2_downloader.py` `build_mirror_urls`
- 去掉 `proxy_base = http://127.0.0.1:6801/` 前缀，直接返回 `scheme://domain/target_url`，按用户架构意图让 aria2 直连镜像。
- 保留 `LOCAL_PROXY_PORT` 常量定义（兼容），不再使用。

### 4.2 `downloader.py` `_legacy_download` 改为多代理并行分片下载
- proxy_list 按 speed 排序（快的在前）。
- 等待后台探测拿到 total_bytes（限时）；拿到后：
  - 预分配 output_path 为 total_bytes。
  - 按切片大小（默认 4MB，切片数上限 8）分成若干片。
  - 每片分配一个代理（速度快的代理优先，循环分配），独立线程用 `Range: bytes=start-(end-1)` 分片下载，seek 写入对应偏移。
  - 每片失败后在本片线程内换下一个代理重试（串行尝试剩余代理）。
  - 实时累加 confirmed_bytes → 0.5s ticker 上报进度。
- total_bytes 探测失败（<=0）时，回退单流顺序尝试（保留现有逻辑）。
- 所有片成功 → 校验文件大小 → completed。

## 5. 待修改文件清单
1. `github_speedup/core/aria2_downloader.py`（build_mirror_urls 直连）
2. `github_speedup/core/downloader.py`（_legacy_download 并行分片）

## 6. 实际改动清单（已执行）
- `aria2_downloader.py` `build_mirror_urls`：去掉 `http://127.0.0.1:6801/` 前缀，直接返回 `scheme://domain/target_url`。
- `downloader.py` `_legacy_download`：
  - proxy_list 按 speed 升序排序（快的在前）。
  - 等待后台探测 total_bytes（限时 min(task.timeout,10)）。
  - total_bytes>0 → 预分配文件 + 按 4MB/8 片上限并行分片，每片独立线程 `Range: bytes=start-(end-1)` + seek 写入，片失败换下一个代理重试，实时累加 confirmed_bytes。
  - total_bytes<=0 → 保留原单流顺序尝试逻辑。
- `downloader.py` `_extract_used_proxy` 与 aria2 complete 分支的域名解析：改为解析直连 URL hostname（不再依赖 6801 前缀）。
- `downloader.py`：移除 viper 代理（6801）启动/停止——aria2 已直连镜像，viper 不再是下载组件必经之路。
- 删除 `downloader.py` 对 `LOCAL_PROXY_PORT` 的 import（不再使用）。

## 7. 测试记录（2026-07-31）
### 环境
Windows，Python 源码运行，网络为直连镜像代理（gh.felicity.ac.cn / g.blfrp.cn / gh.sixyin.com / gh.ddlc.top 支持 206 Range）。

### 测试 1：真实 URL 探测与 Range
- URL: `AI-SSH-Assistant-1.8.23-setup-x64.exe`
- 结果：gh.felicity.ac.cn / g.blfrp.cn / gh.sixyin.com / gh.ddlc.top 均返回 206，Content-Range `bytes 0-1023/143654078`（真实大小 137MB）。gh-proxy.net 返回 200 无 CL；github.geekery.cn 连接错误。
- 判定：PASS

### 测试 2：aria2 直连镜像
- 方式：aria2c `--check-certificate=false` + 完整浏览器头 + split=4
- 结果：0B/0B 卡死 60s+（连接建立但服务器不返回数据），aria2 自带 TLS 与镜像不兼容。
- 判定：FAIL（已确认 aria2 在当前环境不可作为主路径，仅保留兜底）

### 测试 3：legacy 并行分片（yt-dlp 18MB）
- 结果：STATUS=completed，11.3s，total=18023276，文件大小一致。
- 进度事件 26 个，中间值逐步增长（MID_EVENTS=12，样本 524834→11470222），无 0→100 跳变。
- 判定：PASS

### 测试 4：legacy 并行分片（AI-SSH-Assistant 137MB 探测+分片启动）
- 结果：探测拿到 143654078；15 秒内已下载 16MB，进度事件 29 个持续增长，status=downloading。
- 判定：PASS

## 8. 总体结论
- 组件下载不再经过本地 9090/6801 代理，直连镜像代理网址（符合用户架构澄清）。
- legacy 并行分片成为可靠主路径，大文件有实时中间进度。
- aria2 保留为兜底，直连镜像（不套本地代理前缀）。
