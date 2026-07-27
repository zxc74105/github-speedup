# 调研报告：速度虚高 + 代理记录显示问题

## 问题清单

| # | 问题 | 用户描述 | 严重程度 |
|---|------|----------|----------|
| 1 | 下载速度虚高 | 显示 3.4 Mbps，实际约 100 KB/s (0.8 Mbps) | 高 |
| 2 | 代理总大小永远 0.0 GB | 137MB 下完显示 0.0 GB | 中 |
| 3 | 代理最近使用只显示日期 | "2026/7/28" 看不出分钟级差异 | 低 |

---

## 问题 1：速度虚高 — 全链路追溯

### 数据流

```
Worker 读取字节
  → totalDownloaded += n  (core/downloader.go)
  → calcSpeed() 返回 bytes/s  (core/downloader.go:233-248)
  → ProgressData.Speed      (core/downloader.go:265-269)
  → onProgress → EventsEmit (bindings/download.go:169-171)
  → 前端 formatSpeed()       (DownloadPage.tsx:151-155)
    → (speed * 8) / 1_000_000 = Mbps
```

### 各环节验证

**Worker 计数（已确认正确）**
每读取 n 字节就累加到 `totalDownloaded`，单位字节 ✓

**calcSpeed（已确认正确）**
```go
return float64(speedHistory[last].bs-speedHistory[first].bs) / d  // bytes/秒
```
10 秒滑动窗口平均，单位 字节/秒 ✓

**formatSpeed（已确认正确）**
```typescript
const mbps = (speed * 8) / 1000000  // bytes/s × 8 = bits/s, /1M = Mbps
```
1 Mbps = 1,000,000 bps，公式正确 ✓

### 根因：totalDownloaded 双倍计数（double-counting）

Worker 在读取循环中每读到 n 字节就立即 `totalDownloaded += n`。如果：
1. Part 通过 Proxy A 读取了 500KB → `totalDownloaded += 500KB`
2. 网络超时，Part 标记为失败
3. Retry 通过 Proxy B 重新下载整个 Part（4MB） → `totalDownloaded += 4MB`
4. 最终 `totalDownloaded` = 4.5MB，但实际有效数据只有 4MB

**放大效应**：文件 137MB / 4MB = 35 个 parts。假设 20 个 worker，每个初始尝试失败 2 次后才成功（每次读 500KB 后超时）：
- 有效下载：35 × 4MB = 140MB
- totalDownloaded = 140MB + 35 × 2 × 500KB = 140MB + 35MB = **175MB**
- 速度虚高：175/140 = **1.25x**

若失败更频繁或读取更多字节后才失败，虚高倍数更大。

### 修复方案

分离两个计数器：
- `rawDownloaded`：Worker 实时累加（用于展示，不参与速度计算）
- `confirmedBytes`：仅在 Part 成功完成时累加 `r.size`（用于速度和进度）

`calcSpeed()` 和 progress ticker 改用 `confirmedBytes`。

---

## 问题 2：代理总大小永远 0.0 GB

### 代码定位

`frontend/src/pages/ProxyPage.tsx:149`：
```typescript
render: (v: number) => v ? (v / (1024 * 1024 * 1024)).toFixed(1) + ' GB' : '-'
```

**硬编码除以 1024³（1GB）**。对于 137MB = 143,654,912 字节：
```
143,654,912 / 1,073,741,824 = 0.1337 → toFixed(1) → "0.1 GB"
```
所有小于 1GB 的值都显示为 `0.x GB`。小于 50MB 的直接显示 `0.0 GB`。

### 修复方案

复用 `DownloadPage.tsx:144-149` 已有的 `formatBytes` 函数，自动缩放 B/KB/MB/GB。或者提取为共享工具函数。

---

## 问题 3：代理最近使用只显示日期

### 代码定位

`frontend/src/pages/ProxyPage.tsx:150`：
```typescript
render: (v: string) => v ? new Date(v).toLocaleDateString() : '从未'
```

`.toLocaleDateString()` 只返回日期部分（如 `"2026/7/28"`），丢弃了时:分:秒。同一天内的多次下载显示完全一样。

### 修复方案

改为 `.toLocaleString()` 或 `.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })`，输出 `7/28 15:30` 格式。

---

## 附加发现：AverageSpeed 单位不一致

### 代码定位

- `bindings/download.go:174` (`recordSuccess`) 从下载器收到 `calcSpeed()` = **bytes/sec**
- `bindings/server.go:155` (`RecordProxySuccess`) 从被动代理收到 `float64(bytesWritten) / elapsed * 8 / 1_000_000` = **Mbps**

两个不同单位存入同一个 `ProxyRecord.AverageSpeed` 字段。ProxyPage 当前不显示速度，暂无影响，但后续若要显示速度会混乱。

---

## 修改建议优先级

| 优先级 | 问题 | 影响 | 工作量 |
|--------|------|------|--------|
| P0 | 速度 double-counting | 用户感知速度不准确 | 小（backend 改 3 处） |
| P1 | 代理总大小单位 | 记录完全不可读 | 极小（前端 1 行） |
| P2 | 代理时间格式 | 影响测试观察 | 极小（前端 1 行） |
| P3 | AverageSpeed 单位统一 | 潜在问题 | 小（确认即可） |

---

## 涉及文件

- `core/downloader.go` — `totalDownloaded` → `confirmedBytes` 分离（3 处替换 + 2 处新增）
- `frontend/src/pages/ProxyPage.tsx` — totalBytes 格式、lastUsedAt 格式

## 实际修改（已执行）

| 文件 | 改动 |
|------|------|
| `core/downloader.go:230` | `var totalDownloaded int64` → `var rawDownloaded int64` + `var confirmedBytes int64` |
| `core/downloader.go:237` | `calcSpeed` 采样从 `bs: totalDownloaded` → `bs: confirmedBytes` |
| `core/downloader.go:262` | progress ticker `d :=` → `confirmedBytes` |
| `core/downloader.go:339` | Worker 累加 `totalDownloaded` → `rawDownloaded` |
| `core/downloader.go:417` | 结果处理成功时新增 `confirmedBytes += r.size` |
| `core/downloader.go:480` | Retry worker 累加 `totalDownloaded` → `rawDownloaded` |
| `core/downloader.go:504` | Retry 成功时新增 `confirmedBytes += written` |
| `core/downloader.go:567` | 最终进度 `Downloaded: totalDownloaded` → `confirmedBytes` |
| `frontend/ProxyPage.tsx:149` | `÷ 1024³ GB` → `÷ 1024² MB` |
| `frontend/ProxyPage.tsx:150` | `.toLocaleDateString()` → `.toLocaleString('zh-CN', {月,日,时,分})` |
