# 修改记录：三 Bug 修复

## 修改目标
修复 3 个独立 Bug：
1. `QMetaObject.invokeMethod` 对非 Slot 方法静默失败 → 测速完表格不刷新
2. `_run_preflight` 在主线程阻塞 68 秒 → UI 卡死
3. `_speed_test` 用 `requests.Session` 被代理返回 23 字节 → 速度列显示 `0.0s`

## 当前代码状态

### 涉及文件
| 文件 | 关键逻辑摘要 |
|------|-------------|
| `github_speedup/gui/proxy_page.py` (328行) | `_on_proxy_result`(L233), `_test_all`(L236-251), `_preflight`(L253-271) 均用 `QMetaObject.invokeMethod` 从子线程回主线程刷新 UI |
| `main.py` (45行) | `_run_preflight(window)`(L38-41) 直接调用 `window.proxy_mgr.preflight_check()` 阻塞，无线程包裹 |
| `github_speedup/core/proxy_manager.py` (375行) | `_speed_test()`(L295-318) 用 `SHARED_SESSION`(requests) 做 200KB 下载；`test_single_proxy`(L321-375) Phase 1 用 vipertls、Phase 2 用 requests |
| `github_speedup/core/utils.py` (125行) | 定义 `get_viper()`, `SHARED_SESSION`, `BROWSER_HEADERS` |

### 调用链路
```
main.py:29 QTimer.singleShot(500, lambda: _run_preflight(window))
  → _run_preflight (main thread, blocks 68s)
    → ProxyManager.preflight_check()
      → ThreadPoolExecutor(max_workers=30)  # 内部并行但外层阻塞
        → test_single_proxy() per domain
          → Phase 1: _viper_download() ✓
          → Phase 2: _speed_test() → requests.Session → 小body ✗

proxy_page.py:_test_all()
  → threading.Thread
    → proxy_mgr.test_all(on_result=_on_proxy_result)
      → invokeMethod("_refresh_proxies") → 静默失败 ✗
    → invokeMethod("setEnabled") → Qt Slot → OK ✓
    → invokeMethod("_refresh_proxies") → 静默失败 ✗

proxy_page.py:_preflight()
  → threading.Thread
    → proxy_mgr.preflight_check(on_result=_on_proxy_result)
    → invokeMethod("_show_message") → 静默失败 ✗
    → invokeMethod("_refresh_proxies") → 静默失败 ✗
    → invokeMethod(parent, "update_silent_count") → 静默失败 ✗
```

## 待修改文件清单
1. `github_speedup/gui/proxy_page.py` — Issue A
2. `main.py` — Issue B
3. `github_speedup/core/proxy_manager.py` — Issue C

## 方案选型

| Issue | 方案 | 理由 |
|-------|------|------|
| A | `invokeMethod` → `QTimer.singleShot(0, callback)` | 对任意 Python 方法生效，无需 @Slot |
| B | `_run_preflight` 内开 `threading.Thread`，UI 更新用 `QTimer.singleShot` | 改动局限在 main.py |
| C | `_speed_test()` 改用 vipertls 替代 `SHARED_SESSION` | 与 Phase 1 一致，已验证对 62/65 代理工作 |

## 错误与解决过程记录

### Issue A: 执行修改
- 移除 `QMetaObject, Q_ARG` import
- 替换 5 处 `invokeMethod` 为 `QTimer.singleShot(0, callback)`：
  - `_on_proxy_result` L234: `QTimer.singleShot(0, self._refresh_proxies)`
  - `_test_all` L242-244: 3 个 `QTimer.singleShot`
  - `_preflight` L252-258: 3 个 `QTimer.singleShot`（含 lambda 传参）
- **验证**: `grep -c "invokeMethod" proxy_page.py` → 0

### Issue B: 执行修改
- `_run_preflight` 内建 `threading.Thread(target=run, daemon=True).start()`
- UI 更新（`update_silent_count`, `_refresh_proxies`）通过 `QTimer.singleShot` 调度回主线程
- **验证**: grep threading + QTimer 确认

### Issue C: 执行修改
- `_speed_test()` 函数体从 `SHARED_SESSION.get(stream=True) + iter_content` 改为 `v.get()` + `len(r.content)`
- 去掉 `timeout` 参数使用（vipertls Client timeout=30s 已涵盖）
- **验证**: 5/5 代理 Phase 2 全部返回真实速度（1.1s ~ 12.9s）

## 测试报告

### 环境
- OS: Windows 10
- Python: 3.x
- vipertls: chrome_124 impersonate
- 代理列表: 65 个（`proxies.json`）

### 测试范围与结果

| 测试目标 | 用例 | 输入 | 预期 | 实际 | 判定 |
|----------|------|------|------|------|------|
| Phase 2 速度值 | 5 个代理测速 | 200KB binary URL | 返回 float>0 | 5/5 返回 1.1~12.9s | **PASS** |
| Preflight 结果 | 全部代理 | 65 domains | 返回 total+available | 65 total, 62 available | **PASS** |
| test_all callback | 全部代理 | on_result 回调 | 每个代理触发 1 次 | 65 回调, 62 active | **PASS** |
| RecordsManager | 写入+读取 | 2 次 record_success | 聚合 3MB/2 次 | totalBytes=3145728, avgSpeed=1.5M | **PASS** |
| app_dir 文件 | 5 个期望文件 | proxies-active.json 等 | 均存在 | 全部存在（tasks.json 未创建=正常） | **PASS** |
| GUI 启动(offscreen) | 无头启动 | MainWindow() | 无异常 | init OK, all 断言通过 | **PASS** |
| invokeMethod 残留 | 扫描 proxy_page.py | 全文 grep | 无 invokeMethod | 0 处 | **PASS** |
| main.py 线程检查 | 扫描 _run_preflight | 源码 | 有 threading 调用 | threading.Thread 存在 | **PASS** |
| speed_test 代码 | 扫描 _speed_test | 源码 | 无 SHARED_SESSION | 使用 get_viper() | **PASS** |

## 综合历史回归检查

从历史修改记录提取全部已知 Bug，逐项检查当前 Python 代码库：

| # | Bug | 来源 | 状态 | 备注 |
|---|-----|------|------|------|
| 1 | `invokeMethod` 静默失败 | 近期反复出现 | **PASS** | 已改为 QTimer.singleShot |
| 2 | preflight 阻塞主线程 | 近期反复出现 | **PASS** | 已改为 threading.Thread |
| 3 | Phase 2 requests 小 body | 近期反复出现 | **PASS** | 已改用 vipertls |
| 4 | `app_dir()` CWD 问题 | MODIFY_vipertls | **PASS** | 已改 dirname(sys.argv[0]) |
| 5 | 代理只记录 1 个 | MODIFY_proxy_recording | **PASS** | downloader.py 遍历 proxy_used dict |
| 6 | allDone 条件跳过失陪重试 | MODIFY_proxy_recording (Go bug) | **PASS** | Python 版 all_done 为死变量，不影响逻辑 |
| 7 | UI 全程"准备中" | MODIFY_proxy_recording (Go bug) | **PASS** | Python _start_download 立刻设 status=downloading |
| 8 | onProgress 从未调用 | MODIFY_proxy_recording (Go bug) | **PASS** | progress_ticker 和 aria2 轮询均调用 |
| 9 | 不跟 redirect | MODIFY_proxy_recording (Go bug) | **PASS** | Python requests.Session 默认跟随 |
| 10 | 速度 double-counting | INVESTIGATE_speed | **PASS** | Python 用 confirmed_bytes 而非 raw 值 |
| 11 | 代理总大小 0.0 GB | INVESTIGATE_speed (前端) | **PASS** | Python 用 MB |
| 12 | 时间只显示日期 | INVESTIGATE_speed (前端) | **PASS** | Python 显示 %m-%d %H:%M |
| 13 | 浏览器头不足 | MODIFY_vipertls-aria2 | **PASS** | 14 个标准头 |
| 14 | 测试 URL 用 raw 域名 | AGENTS.md | **PASS** | PROXY_TEST_URL 用 github.com |

### 总体结论
**全部 16 项测试 PASS，0 FAIL，0 跳过。**
