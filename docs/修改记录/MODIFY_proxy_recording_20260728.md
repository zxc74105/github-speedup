# 修改记录：代理录制问题调研与修复

## 修改目标
修复下载完成后仅记录 gh-proxy.com 一个代理的问题，确保所有成功下载数据的代理都被记录到 proxy-records.json。

## 调研阶段

### 问题现象
执行一个 17.6MB 文件的下载后，`proxy-records.json` 只有一条记录：
```json
{"domain": "gh-proxy.com", "totalBytes": 17581294, ...}
```

### 日志分析与根因追溯

1. **日志属于被动代理，不是主动下载器**
   - `proxy-access.log` 中的 REQUEST/TRY/FAIL/SUCCESS 全部来自 `server.go`（被动 HTTP 代理模式）
   - `downloader.go`（主动分段下载器）完全没有 AccessLogger 调用，无法通过日志追踪

2. **被动代理结果：仅 gh-proxy.com 成功**
   - gh-proxy.com 成功传输 17.6MB (1.9 Mbps)
   - 其余 28 个代理 FALL 日志均为 `context canceled` — 原因是上下文已被客户端断开，不是代理真失败

3. **代码 Bug #1 — `allDone` 条件错误**（`downloader.go:383`，已修复）
   - 原代码：`if !allDone && len(failedParts) > 0` 
   - 效果：只要任意一个 part 成功（`allDone = true`），所有失败 part 永不进入重试循环
   - 后果：第一个 part（分配了 `proxyList[0]=gh-proxy.com`）成功后，其余失败 part 全部丢弃

4. **代码 Bug #2 — 最终只记录最佳代理**（已修复）
   - 原代码只选取 `proxyUsed` 中字节最多的代理记录
   - 结合 Bug #1，`proxyUsed` 只有 gh-proxy.com → 只记录 gh-proxy.com

5. **完整根因链**：
   - 文件 5 个 parts（17.6MB/4MB = 5）
   - Part 0 → proxyList[0]=gh-proxy.com → **成功** → `allDone=true`
   - Part 1-4 → 其他代理 → **失败** → 因 `allDone=true` 不重试 → `proxyUsed` 只有 gh-proxy.com
   - 最终 `recordSuccess` 只输出 gh-proxy.com

### 缺失的日志能力
主动下载器的 worker 和 retry 循环都没有调用 AccessLogger，导致运行时完全无法追踪每个 proxy 的尝试结果。

## 计划修改

### 修改 1：给下载器添加 AccessLogger 调用
在以下位置添加日志：
- Worker 处理 job 成功/失败时
- Retry 循环每次尝试时

### 修改 2：确认 Bug #1 和 Bug #2 已修复
Bug #1（allDone 条件）和 Bug #2（只记录最佳）已在上一轮修改中修复。
需要在本次构建后通过日志验证。

## 后续发现的问题

### Bug #3 — UI 全程显示"准备中"
**现象**：下载任务创建后，UI 一直显示"准备中"，即使后台已开始下载。
**根因**：CreateTask 的 goroutine 只在下完成后才更新 `taskInfo.Status`。下载期间 `StartBackgroundDownload` 内部修改了 `t.Status`，但那是 `core.DownloadTask` 对象，UI 读取的是 `TaskInfo.Status`。两者是不同对象，没有任何同步机制。

**修复**：在调用 `StartBackgroundDownload` 之前立即设置 `taskInfo.Status = "downloading"` 并保存。

### Bug #4 — onProgress 回调从未被调用
**现象**：前端收不到进度事件，进度条不更新。
**根因**：`StartBackgroundDownload` 接受 `onProgress` 参数但从未调用它。`bindings/download.go` 中定义的 `onProgress` 闭包（调用 `runtime.EventsEmit`）只存在于代码中，从未被执行。最后结束时通过独立 `EventsEmit` 发送一次完成事件。

**修复**：
- 在 `StartBackgroundDownload` 中添加定时器（500ms），定期通过 `onProgress` 上报当前下载量和速度
- 在下载结束时通过 `onProgress` 上报最终数据
- 在 bindings 的闭包中自动注入 `TaskID`，使前端能正确匹配到对应任务

### Bug #5 — SharedTransport.RoundTrip 不跟 redirect
**现象**：Worker 和 retry 使用 `Transport.RoundTrip` 直接请求，不跟随 3xx 重定向；而被动代理和 HEAD 探测使用 `Client.Do` 会跟随。可能导致部分需要重定向的代理在下载时失败，但在测试时通过。

**修复**：创建 `SharedClient` 封装 `SharedTransport`，Worker 和 retry 改用 `SharedClient.Do(req)`。

### Bug #6 — AccessLogger 在 bindings 包造成循环依赖
**现象**：core 包无法调用 AccessLogger（会循环依赖 bindings）。
**修复**：将 AccessLogger 类型和 `InitLogger()`/`GetLogger()` 移到 `core/logger.go`。`bindings/logger.go` 改为薄包装，调用 `core` 的实现。

## 涉及文件
- `D:\AI-Projects\github-speedup\core\downloader.go` — 添加 AccessLogger、进度定时器、SharedClient
- `D:\AI-Projects\github-speedup\core\utils.go` — 添加 SharedClient 变量
- `D:\AI-Projects\github-speedup\core\logger.go` — 新建，AccessLogger 从 bindings 移入
- `D:\AI-Projects\github-speedup\bindings\logger.go` — 简化为 core 的薄包装
- `D:\AI-Projects\github-speedup\bindings\download.go` — goroutine 内提前设置 downloading 状态、注入 TaskID、改用 onProgress
