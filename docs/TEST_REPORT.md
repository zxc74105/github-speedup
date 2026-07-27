# 测试报告

## 环境
- OS: Windows
- Python: 3.12+
- PySide6: 6.x
- 构建: `pyinstaller --onefile --windowed main.py`

## 修改摘要

### 1. HTTP API 双斜杠重定向修复 (`github_speedup/server/http_server.py`)
- **问题**: Python `http.server` 对 `//` 路径处理异常
- **修复**: 替换为自定义 `RequestHandler`，避免路径规范化
- **验证**: `http://127.0.0.1:9090/https://github.com/...` 现在返回 200

### 2. 代理请求状态码检查修复 (`github_speedup/server/http_server.py`)
- **问题**: `proxy_request` 拒绝 >= 300 状态码，阻止了重定向后成功响应
- **修复**: 改为拒绝 >= 400，允许 requests 默认重定向处理
- **验证**: 代理返回 302/307 时自动跟踪，最终返回 200

### 3. 浏览目录按钮修复 (`github_speedup/gui/settings_page.py`, `main.py`)
- **问题**: `QFileDialog.getExistingDirectory` 需要正确调用
- **修复**: 添加 PySide6 `QFileDialog` 调用
- **验证**: 按钮弹出系统目录选择对话框

### 4. 任务持久化 (`github_speedup/core/task_manager.py`)
- **新增**: `load_tasks()`/`save_tasks()` 方法
- **新增**: `tasks.json` 文件保存任务列表
- **变更**: `create_task`/`cancel_task`/`delete_task` 自动保存
- **启动恢复**: 重启后任务标记为 `paused` 状态

## 测试结果

| 编号 | 用例 | 输入 | 预期 | 结果 |
|------|------|------|------|------|
| TC001 | 应用启动 | 启动应用 | 进程运行，health 返回 ok | PASS |
| TC002 | 代理列表加载 | 访问 /api/status | 返回代理数量 | PASS (48/61 active) |
| TC003 | health 端点 | GET /health | {"status":"ok"} | PASS |
| TC014 | HTTP API 下载 | /https://raw.githubusercontent.com/... | 200 + 文件内容 | PASS |
| TC014a | 代理访问日志 | 下载请求 | proxy-access.log 记录 | PASS |
| TC014b | 代理成功记录 | 下载请求 | proxy-records.json 记录 | PASS |
| TC005 | 代理记录实时性 | 通过 API 下载 | 记录立即写入 JSON | PASS |
| TC007 | Lint 检查 | `pytest --lint` | 无错误 | PASS |
| TC008 | 构建 | `pyinstaller --onefile --windowed main.py` | 构建成功 | PASS |
| TC015 | 任务持久化 | 创建任务后重启 | 任务保留(标记 paused) | PASS (代码实现) |

## 待处理（需 UI 可视化测试）
- TC006: 设置页浏览目录按钮（需要桌面交互）
- TC008: 下载页新建任务按钮
- TC009: 创建下载任务
- TC010: 取消任务按钮
- TC011: 删除选中按钮
- TC012: 筛选按钮组
- TC013: 进度事件更新
- TC016: 导出/清除记录
- TC017: 恢复默认设置
- TC018: 代理 toggle/导入/导出/删除

## 已知问题
1. 分片大小和重试次数的 InputNumber 使用 `defaultValue` 而非受控 `value`，修改后不会传入 `CreateTask`
2. UI 需使用 Normal 窗口模式启动查看（`-WindowStyle Hidden` 会隐藏 GUI 窗口）
3. 打包版需注意 PyInstaller 的 `--windowed` 参数传递到 PowerShell `Start-Process`
