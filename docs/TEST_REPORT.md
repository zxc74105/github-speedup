# 测试报告

## 环境
- OS: Windows
- Python: 3.12+
- PySide6: 6.x
- 构建: `pyinstaller build.spec`

## 修改摘要

### 1. 代理测速重写 (`proxy_manager.py`)
- vipertls 线程本地客户端 + 直接调用（无内层线程），恢复 Chrome TLS 指纹
- 两阶段测速：34B 连通性 → 200KB 体速
- 30 线程池 + as_completed 实时 GUI 刷新
- 状态简化为"可用/不可用"

### 2. 下载引擎 (`downloader.py`)
- 下载组件直连镜像代理网址（不经过本地 9090/6801 代理）
- legacy 并行分片为主路径：代理按速度排序 + Range 分片 + 每片独立线程直连镜像 + 失败换代理重试 + 实时进度
- aria2 为兜底：build_mirror_urls 直连镜像
- 修复失败分片静默跳过的问题
- 修复 aria2 路径不记录代理成功记录的问题
- 移除 viper 代理（6801）的启动/停止

### 3. 本地 vipertls 代理 (`local_viper_proxy.py`)
- 遗留模块：下载组件已不再使用（组件直连镜像）

### 4. 下载页 (`download_page.py`)
- 修复下载进度/速度/总大小不显示的问题（字段名 total_bytes → totalBytes）
- 删除确认对话框直接删任务+本地文件

### 5. 代理页 (`proxy_page.py`)
- 清空记录无确认框
- 实时测速结果刷新

### 6. GUI 状态显示
- 移除 silent/checking/offline 等多余状态
- 仅显示可用（绿）和不可用（红）

## 测试结果

| 编号 | 用例 | 结果 |
|------|------|------|
| TC001 | 应用启动 | PASS |
| TC002 | 代理列表加载 | PASS |
| TC003 | 全部测速按钮 | PASS |
| TC004 | 代理预检按钮 | PASS |
| TC005 | 代理记录显示 | PASS |
| TC006 | 设置页浏览目录 | PASS |
| TC007 | 设置保存 | PASS |
| TC008 | 新建任务对话框 | PASS |
| TC009 | 创建下载任务 | PASS |
| TC010 | 取消任务 | PASS |
| TC011 | 删除任务（含文件） | PASS |
| TC012 | 筛选按钮 | PASS |
| TC013 | 进度事件更新 | PASS |
| TC014 | HTTP API 下载 | PASS |
| TC015 | 任务持久化 | PASS |
| TC016 | 导出/清除记录 | PASS |
| TC017 | 恢复默认设置 | PASS |
| TC018 | 代理导入/导出/删除 | PASS |

## 待处理
- docs/ 架构视图文档（01-20）引用已删除的 api/ 层，需要重写

## 已知问题
1. 无
