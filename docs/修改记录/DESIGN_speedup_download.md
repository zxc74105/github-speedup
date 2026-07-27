# DESIGN: 分段下载加速方案

## 架构变更

### 修改前（每次分片独立建连）
```
Worker 1 → 新建 Transport → TCP+TLS → 代理A → 下载 10MB → 关闭连接
Worker 2 → 新建 Transport → TCP+TLS → 代理B → 下载 10MB → 关闭连接
Worker 3 → 新建 Transport → TCP+TLS → 代理A → 再次 TCP+TLS(!) → 下载 10MB
```

### 修改后（共享 Transport 复用连接）
```
包级 Transport (MaxIdleConns=100, MaxIdleConnsPerHost=10, IdleConnTimeout=90s)
  │
  ├─ Worker 1 → 代理A → 复用连接(keep-alive) → 下载 50MB
  ├─ Worker 2 → 代理B → 复用连接(keep-alive) → 下载 50MB
  ├─ Worker 3 → 代理A → 复用已有连接(!) → 下载 50MB
  └─ ...
```

## 详细改动

### 1. `core/utils.go` — 共享 Transport

```go
var SharedTransport = &http.Transport{
    DialContext: (&net.Dialer{
        Timeout:   5 * time.Second,
        KeepAlive: 30 * time.Second,
    }).DialContext,
    TLSHandshakeTimeout:   5 * time.Second,
    ResponseHeaderTimeout: 5 * time.Second,
    TLSClientConfig:       &tls.Config{InsecureSkipVerify: true},
    MaxIdleConns:          100,
    MaxIdleConnsPerHost:   10,
    IdleConnTimeout:       90 * time.Second,
}
```

`DownloadPartialFile` 改为使用共享 Transport（移除内部的 `transport := &http.Transport{...}`）：

```go
func DownloadPartialFile(ctx context.Context, fileURL, proxyURL, outputPath string, startByte, endByte int64, timeout time.Duration, onProgress func(int64)) (int64, error) {
    client := &http.Client{Transport: SharedTransport}
    // ... 其余不变
}
```

### 2. `core/downloader.go` — 调整默认参数

- `MaxConcurrent`: 20 → 8
- `PartSizeBytes`: 10MB → 50MB

```go
// 在 StartBackgroundDownload 中
if task.MaxConcurrent == 0 {
    task.MaxConcurrent = 8  // 原来是 20
}
if task.PartSizeBytes == 0 {
    task.PartSizeBytes = 50 * 1024 * 1024  // 原来是 10 * 1024 * 1024
}
```

## 预期收益计算

| 指标 | 改前 | 改后 | 说明 |
|------|------|------|------|
| 每分片建连开销 | 0.5-3s | 0s（复用） | 共享 Transport |
| 并发 worker 数 | 20 | 8 | 减少代理争抢 |
| 分片大小 | 10MB | 50MB | 减少分片数 5x |
| 总连接数（500MB 文件） | 50 次建连 | ~2-5 次建连 | 连接复用 |

## 回滚方案
回滚上述两文件的修改即可。
