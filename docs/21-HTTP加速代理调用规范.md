# HTTP 加速代理调用规范

## 概述

本软件提供**两种使用模式**：

| 模式 | 说明 | 谁在用 |
|------|------|--------|
| **主动下载**（GUI） | 桌面 GUI 操作，多代理并行分片下载 | 终端用户 |
| **被动加速**（HTTP 服务） | 端口 9090 HTTP 透明代理 | 浏览器/curl/aria2/脚本 |

## 被动加速模式

### 原理

```
任何 HTTP 客户端               本软件 HTTP 服务 (端口 9090)
┌──────────────┐              ┌──────────────────────────────┐
│ curl / 浏览器  │── GET ──→    │  接收请求                     │
│ aria2 / IDM   │   /<目标URL> │  从代理池挑选最优代理          │
│ Python 脚本   │              │  将请求原样转发到目标          │
│ 任何 HTTP 客户端│←── 响应 ──│  响应流原样返回               │
└──────────────┘              │  失败自动换代理重试            │
                              └──────────────────────────────┘
```

### 用法

```bash
# curl
curl -O http://127.0.0.1:9090/https://github.com/.../file.zip

# wget
wget http://127.0.0.1:9090/https://github.com/.../file.zip

# aria2 (自带多线程)
aria2c -x 8 http://127.0.0.1:9090/https://github.com/.../file.zip

# 浏览器：直接地址栏输入
http://127.0.0.1:9090/https://github.com/.../file.zip

# Python
import requests
r = requests.get("http://127.0.0.1:9090/https://github.com/.../file.zip", stream=True)
```

### 行为规范

| 特性 | 说明 |
|------|------|
| 请求格式 | `GET /<完整目标URL>` — 完整 URL 放在路径中 |
| 请求方法 | 支持 GET / HEAD |
| 头部透传 | 所有请求头原样转发（Range/User-Agent/Cookie 等） |
| 响应透传 | Content-Type/Content-Disposition/Accept-Ranges 全部透传 |
| Range 支持 | ✅ aria2/IDM 可用多连接分段下载 |
| 失败重试 | 自动换代理重试，调用方无感知 |
| 文件名 | 由源站 Content-Disposition 决定，调用方自己处理 |
| 保存位置 | **调用方的责任**，本软件不保存 |
| 浏览器 URL 修复 | 自动处理 `//` → `/` 规范化（https:/ 恢复为 https://） |

### 代理选择策略

```
请求到达
  │
  ├── 遍历代理列表（Status=active, Enabled=true, Scheme!=""）
  │   ├── 依次尝试
  │   │   └── proxyRequest() → 成功? → 返回
  │   └── 失败 → 下一个
  └── 全部失败 → 502 Bad Gateway
```

### 健康检查端点

| 端点 | 方法 | 返回 |
|------|------|------|
| `/health` | GET | `{"status":"ok"}` |
| `/api/status` | GET | `{"running":true,"availableProxies":N,"totalProxies":N}` |

### 配置

HTTP 加速服务**默认开启**，端口 9090，允许远程访问。通过设置页可修改端口。

### 访问日志

每次请求记录到 `proxy-access.log`（程序运行目录）：
```
[2026-07-26 12:00:00.000] REQUEST https://github.com/... from 127.0.0.1:54321
[2026-07-26 12:00:00.100] TRY gh-proxy.com
[2026-07-26 12:00:01.500] SUCCESS gh-proxy.com - 1048576 bytes, 12.3 Mbps
```
