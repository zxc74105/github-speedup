# ALIGNMENT: 代理检测加速方案

## 问题陈述

### 业务约束（不可妥协）
- **vipertls 必须用于代理检测**。不用 vipertls 时 29 个代理中只有约 15 个可用（active）；用了 vipertls 后约 25 个可用。这是用户核心需求。
- **检测必须并行**，不能一个一个测。

### 技术问题
1. **vipertls 的 timeout 参数失效**：`vipertls.Client(impersonate="chrome_124", timeout=3)` 设置 3s 超时，实际一个请求可能跑 12s+。原因不明（可能是内部自定义 socket 操作绕过了 requests 的 timeout 传递）。
2. **单个 TLS 连接慢**：每次 vipertls 发起 HTTPS 请求，TLS 握手（含 Chrome 指纹模拟）耗时 1~20s 不等，取决于代理 CDN 的网络状况。
3. **Python 线程无法被杀死**：`concurrent.futures.Future.result(timeout=N)` 虽然会抛出 TimeoutError，但背后的线程继续运行，无法强制终止。
4. **套接字级 timeout 也不管用**：`socket.setdefaulttimeout()` 被 vipertls 内部绕过。
5. **Windows 无 signal.alarm**：无法用 UNIX 的信号机制实现线程级超时。

### 关键数据
- 29 个代理，20 线程并行
- 用 vipertls+正确超时：目标 ≤20s 完成全部检测
- 用 vipertls+无超时：实测 25~40s
- 不用 vipertls：15s 但只有 15 个代理可用

## 候选方案对比

### 方案 A：ThreadPoolExecutor 包裹硬超时（推荐）

**原理**：在 `test_single_proxy` 内部包一层 `ThreadPoolExecutor(max_workers=1)`，提交实际测试任务后 `future.result(timeout=10)`。超时则返回 offline，背后线程成为"孤儿线程"继续运行，最终自动退出。

**优点**：
- 改动最小，只改 `test_single_proxy` 函数体
- 超时精确，不受 vipertls 内部 timeout 失效影响
- 线程最终自己结束（socket 操作完成或进程退出时回收）
- 每个线程独立 vipertls.Client（`get_viper()` 已经是 thread-local）

**缺点**：
- 产生孤儿线程：超时线程在后台继续跑至 socket 结束，数量 = 超时代理数 ≤ 10 个
- 嵌套 Executor：外层 20 线程 + 内层 1 线程 = 最多 40 个线程同时存在
- 理论上线程泄漏，但对桌面工具来说无关紧要（进程退出就全没了）

**预期效果**：
- 29 代理 × 每个最多 10s / 20 线程 ≈ 15~20s 完成
- 真正超时的代理标记为 offline，不卡住队列

### 方案 B：multiprocessing.Process + 可杀进程

**原理**：为每个代理测试启动独立子进程，`process.join(timeout=10)` 超时后 `process.terminate()` 强制杀死。

**优点**：
- 进程可被强制杀死，无泄漏
- 超时精确

**缺点**：
- 进程启动开销大（每个 ~0.3~0.5s），30 个代理额外加 10~15s
- 进程间通信复杂（Queue/Pipe 传结果）
- Windows 下 `spawn` 模式启动更慢
- 总共时间反而可能更长

### 方案 C：二阶段检测（用户已否决）

**原理**：先用 requests.Session 快速检测（连通性），再用 vipertls 验证 TLS 指纹。

**缺点**：用户明确否决（"检测的时候必须使用vipertls"）。

### 方案 D：asyncio + 超时

**原理**：把检测改为异步，用 `asyncio.wait_for(coro, timeout=10)` 实现超时。

**优点**：
- 超时精确
- 不产生孤儿任务

**缺点**：
- vipertls 是同步库，需用 `loop.run_in_executor` 跑，又回到线程问题
- 架构改动大，GUI 集成复杂
- 实际收益不如方案 A

### 方案 E：修补 vipertls timeout

**原理**：找到 vipertls 内部为什么不尊重 timeout，修复它。

**缺点**：
- vipertls 是第三方闭源/无法追溯的库
- 无法保证修复后对其他功能无影响
- 时间不可控

## 推荐方案：A

选择方案 A（ThreadPoolExecutor 包裹硬超时），原因：
1. 改动最小
2. 效果可预期
3. 对桌面应用来说孤儿线程不是问题
4. 用户要求的多线程 + vipertls 同时满足

---

**下一步**：进入 Architect 阶段，设计 `test_single_proxy` 的新结构。
