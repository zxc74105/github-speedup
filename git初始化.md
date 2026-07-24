# Git Setup Guide

本文件夹下的 `init-git.sh` 可一键初始化新项目的 git 仓库。
以下是它的具体做了哪些事、以及注意事项。

## 脚本做了什么

1. `git init` — 创建 `.git`
2. 创建 `.gitignore` — 包含常见的 node_modules、.env、构建产物、AI 工具状态目录
3. **文件数量检查** — 如果首次 commit 要跟踪超过 500 个文件，脚本会拒绝并提示你先完善 .gitignore
4. `git add . && git commit -m "chore: initial commit"` — 干净的首次提交
5. 打印 AGENTS.md 中需要的 git 工作流规则

## .gitignore 注意事项

脚本生成的 .gitignore 底部有一段 `CUSTOMIZE` 区，**必须根据项目手动修改**：

```gitignore
# ── CUSTOMIZE: add project‑specific ignore patterns below ──
# /参考/
# /借鉴资料/
# data/
# credentials.json
```

把不需要被 git 追踪的大目录取消注释或添加进去。**这一步很重要**，否则会出现像 25k 文件被错误跟踪的问题。

## AGENTS.md 规则

脚本运行完后，**需要手动把输出的 git 工作流规则粘贴到 `AGENTS.md` 中**。规则内容：

- **禁止自动提交** — 修改文件后不要自动 commit，让 OpenCode 显示待处理变更
- **仅当用户要求时才提交**
- **仅当用户要求时才推送**
- **撤销用 `git checkout -- <file>` 或 `git restore <file>`**
- **暂存用 `git stash push -u`**

## 完美状态的标准

初始化完成后应该：

```
$ git log --oneline
xxxxxxxx chore: initial commit

$ git status
nothing to commit, working tree clean
```

首次 commit 的文件数应该合理（<500，视项目而定）。
如果有大量文件被跟踪，说明 .gitignore 还没写完整。

## 直接跑

```bash
cd 你的新项目目录
bash /path/to/init-git.sh
```
