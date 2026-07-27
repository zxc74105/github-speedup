# AGENTS.md

> **优先级说明**：全局规则（`rules.md` / `negative-rules.md`）为最高准则，本文件补充项目专用规则。冲突时以全局规则为准。

## 工作流：6A 开发流程（强制）

所有开发任务必须按以下六阶段执行（重要/复杂任务走全流程，简单任务可跳过不必要阶段）：

### 1. Align（对齐）
- 分析项目结构、技术栈、架构模式、依赖关系[reference:33]
- 创建 docs/任务名/ALIGNMENT_[任务名].md[reference:34]
- 质量门控：需求边界清晰、验收标准可测试[reference:35]

### 2. Architect（架构）
- 基于 ALIGNMENT 文档设计架构[reference:36]
- 生成 DESIGN_[任务名].md，含架构图(mermaid)、接口契约[reference:37]

### 3. Atomize（原子化）
- 将大任务拆解为可独立执行的子任务[reference:38]
- 每个子任务有明确的输入输出和验收标准

### 4. Approve（审批）— 仅重要/复杂任务
- **仅对架构变更、接口设计变更、重大功能改动等复杂任务执行**；简单任务（bug fix、小功能、配置修改等）**跳过本阶段**，Atomize→Automate 直接执行
- 重要任务需人工确认设计/拆分的合理性后再进入 Automate

### 5. Automate（执行）
- 按文档执行，小 diff、频繁检查点
- 自动纠错：编译/运行时错误自动修复

### 6. Assess（评估）
- 质量验收，不合格则返回对应阶段重来[reference:41]
- 产出测试报告

## 编码规范（5S 映射）
- 环境一致性：每次任务前确认依赖版本
- 代码洁癖：函数级注释、测试优先[reference:42]
- 文档同步：代码变更必须同步更新文档

## Review 与 Retro（TWorkflow 补充）
- Review：三种视角审查（功能正确性、架构一致性、代码质量）
- Retro：记录计划偏差，反馈到下一轮计划

## 启动方法
开发模式（源码运行）：
```bash
python main.py
```
打包版本（github-speedup.exe，使用 PyInstaller 构建）：
```bash
powershell -Command "Start-Process -WindowStyle Hidden -FilePath 'D:\AI-Projects\github-speedup\github-speedup.exe'"
```
验证：`tasklist //FI "IMAGENAME eq github-speedup.exe"` 确认进程存在，然后 `curl -s "http://127.0.0.1:9090/health" --max-time 5` 返回 `{"status":"ok"}`。

注意：`cmd /c start ...` 或直接 `&` 后台启动均不可靠，必须用 PowerShell `Start-Process`。

## 关键记录

### 代理测试 URL 注意
GitHub 代理（gh-proxy.com 等）是 URL-prefix 反向代理，只代理 `github.com` 域名。
测试代理时必须用 `https://github.com/...` 格式，**不能用** `https://raw.githubusercontent.com/...`（raw 域名不走代理）。
- 正确测试 URL: `https://github.com/zxc74105/ceshi/blob/main/speedtest.txt`
- 错误测试 URL: `https://raw.githubusercontent.com/zxc74105/ceshi/main/speedtest.txt`
- 代码位置: `github_speedup/proxy/proxy_checker.py` 中 `PROXY_TEST_URL` 常量
- 所有代理列表中的域名都是 URL-prefix 反向代理（不是 CONNECT 代理），构造 URL 格式: `https://代理域名/https://github.com/原始路径`

### 浏览器头模拟
所有出站 HTTP 请求必须携带完整 Chrome 浏览器头，否则很多代理返回 403/HTML 验证页。
- 函数: `github_speedup/core/utils.py` 中 `apply_browser_headers(session: requests.Session)`
- 调用位置: `github_speedup/core/downloader.py`（HEAD + 下载请求）、`github_speedup/proxy/proxy_checker.py`（测速）、`github_speedup/server/http_server.py`（被动加速）
- 包含: User-Agent/Accept/Accept-Language/Sec-Fetch-* 等 14 个标准浏览器头

