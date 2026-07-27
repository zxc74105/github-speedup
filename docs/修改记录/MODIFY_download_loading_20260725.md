# 修改记录：下载按钮加载状态（防重复提交）

## 修改目标
点击"开始下载"后按钮无任何反馈，用户误以为未点击而多次点击，导致后台创建多个下载任务。

## 当前代码状态
- 文件: `frontend/src/pages/DownloadPage.tsx`
- 关键函数: `handleCreateTask`（第 101-120 行）
- `okButtonProps` 仅设置了 `disabled: !url.trim()`，无 loading 状态
- Go 后端的 `CreateTask` 调用 `GetFileInfo`（HEAD 请求获取文件大小），通过网络代理进行，耗时数秒至数十秒，前端无任何视觉反馈

## 计划修改方案
1. 新增 `creating` state（boolean），初始 `false`
2. `handleCreateTask` 执行前 `setCreating(true)`，`finally` 中恢复
3. `okButtonProps` 添加 `loading: creating`，使按钮在任务创建时禁用+转圈

## 待修改文件清单
- `D:\AI-Projects\github-speedup\frontend\src\pages\DownloadPage.tsx`
