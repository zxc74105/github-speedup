# 修改记录: vipertls 参数补全 + aria2 下载核心整合

## 修改目标
1. 所有出站请求用 vipertls 补全 Chrome TLS 指纹参数
2. 用 aria2c 替换 Python 流式下载，提升下载速度

## 架构变更
```
GUI/检测                下载
  │                      │
  ├─ vipertls.Client ────┤  TCP:6801 (本地 forward proxy)
  │                      │
proxy_manager.py    local_viper_proxy.py  → vipertls.Client
                           │
                      aria2c.exe (RPC:6800)
                           │
                      --all-proxy=http://127.0.0.1:6801
```

## 当前代码状态
- `core/utils.py`: `SHARED_SESSION = requests.Session()` — Python 默认 TLS
- `core/proxy_manager.py`: `test_single_proxy` 用 `SHARED_SESSION.get()` + `iter_content()`
- `core/downloader.py`: 用 `SHARED_SESSION.get(stream=True)` + `iter_content()` 流式分片下载
- `gui/download_page.py`: 直接调用 `start_background_download`，使用 threading 监听进度
- `server/proxy_server.py`: 创建独立 `requests.Session()` 转发

## 待修改/新建文件清单
- [新建] `core/local_viper_proxy.py` — 轻量 HTTP forward proxy，用 vipertls.Client 转发
- [新建] `core/aria2_downloader.py` — aria2c 进程管理 + JSON-RPC 控制
- [修改] `core/utils.py` — 添加 `VIPER_CLIENT` 全局对象
- [修改] `core/proxy_manager.py` — `test_single_proxy` 改用 vipertls.Client
- [修改] `core/downloader.py` — 保留 public API，底层调用 aria2_downloader
- [修改] `gui/download_page.py` — 适配 aria2 进度事件
- [修改] `server/proxy_server.py` — 转发用 vipertls.Client
- [新增] `bin/aria2c.exe` — aria2 二进制
