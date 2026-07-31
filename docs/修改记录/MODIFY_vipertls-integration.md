# 修改记录: vipertls 集成

## 修改目标
将 vipertls Client 集成到代理检测流程中，替换 `requests.Session` 以提供 Chrome TLS 指纹，提高代理兼容性。

## 当前代码状态
- `github_speedup/core/utils.py`: `SHARED_SESSION = requests.Session()` — 全局共享会话，由 proxy_manager 和 downloader 共用
- `github_speedup/core/proxy_manager.py`: `test_single_proxy()` 使用 `SHARED_SESSION.get()` 进行代理检测，使用 `resp.iter_content()` 做带宽测速
- `github_speedup/core/downloader.py`: 使用 `SHARED_SESSION.head()` 获取文件大小，`SHARED_SESSION.get(stream=True)` + `iter_content()` 做分段下载
- vipertls `Client` 返回 `ViperResponse`，支持 `.content` 但不支持 `iter_content`/`close`/`raw`

## 计划修改方案
1. `utils.py`: 添加 `VIPER_CLIENT` 懒初始化全局对象（vipertls.Client）
2. `proxy_manager.py`: `test_single_proxy` 改用 `VIPER_CLIENT`，用 `.content` 代替 `iter_content`
3. `downloader.py`: 保持 `SHARED_SESSION` 不变（预检通过的代理仍能用 requests 下载；302 重定向到 raw.githubusercontent.com 不受 TLS 影响）
4. 不改动 vipertls 的 `follow_redirects` 默认值（True）—— 和现有行为一致

## 待修改文件清单
- `github_speedup/core/utils.py`
- `github_speedup/core/proxy_manager.py`
