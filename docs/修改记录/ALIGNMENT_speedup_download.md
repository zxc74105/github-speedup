# ALIGNMENT: 分段下载加速方案

## 问题描述
分段下载速度仅有 1-3 MB/s，而同类工具（刚哥）可达 8-9 MB/s。20 并发 + 10MB 分片的情况下，聚合带宽反而低于单线程下载。

## 瓶颈分析

### 瓶颈 1: 每次分片都新建 HTTP Transport（最严重）
- `DownloadPartialFile()` 每次调用都创建新的 `http.Transport`
- 每次分片下载都要完整经历：DNS 解析 → TCP 三次握手 → TLS 四次握手
- 连接无法复用，keep-alive 完全失效
- 分片越小（10MB），连接开销占比越高

### 瓶颈 2: 并发数过高引发代理争抢
- 20 个 worker 同时竞争 ~48 个代理
- 每个代理同时服务多个请求，互相争抢带宽
- 代理本身带宽有限（通常 1-5 Mbps），20 路并发只会加剧延迟

### 瓶颈 3: 分片过小，收益被开销淹没
- 10MB/片 × 20 并发 = 每片独立建连
- 建连耗时 0.5-3s，传 10MB 耗时 2-10s，开销占比高达 15-60%

### 瓶颈 4: 每片使用不同代理，无法利用 keep-alive
- `ProxyPool.Assign()` 给每个 worker 分配代理
- 不同 part 可能走不同代理，连接无法复用

## 设计方案

### 方案 A: 共享 Transport（核心修复）
- 将 `http.Transport` 从 `DownloadPartialFile` 内部移到包级共享变量
- 设置 `MaxIdleConns: 100`, `MaxIdleConnsPerHost: 10`, `IdleConnTimeout: 90s`
- 使同一代理的多段分片复用 TCP/TLS 连接

### 方案 B: 降低默认并发数
- 从 20 降到 8
- 减少代理争抢，让每个 worker 获得更稳定的代理连接

### 方案 C: 增大默认分片大小
- 从 10MB 增加到 50MB
- 减少分片总数，降低连接开销占比

### 预期效果
- 连接复用：同一代理连续下载多片，免 DNS/TCP/TLS 开销
- 减少争抢：8 路并发 × 50MB 分片，每片建连开销占比降至 5% 以下
- 目标速度：5-10 MB/s（匹配刚哥水平）

## 修改文件清单
- `core/utils.go` — 添加包级共享 Transport，`DownloadPartialFile` 改为接收 Transport 参数
- `core/downloader.go` — 创建共享 Transport 传入 `DownloadPartialFile`；修改默认并发数 20→8；修改默认分片 10MB→50MB
