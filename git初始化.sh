#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────
#  init-git.sh — One-shot git setup for new projects
#  Usage:   cd /path/to/new/project && bash init-git.sh
#  What it does:
#    1. git init
#    2. .gitignore (comprehensive, needs project‑specific edits)
#    3. Warns if >500 files would be tracked (avoid bloating)
#    4. Creates a clean initial commit
#    5. Injects AGENTS.md git workflow rules
# ────────────────────────────────────────────────────────────

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

if [ -d ".git" ]; then
  echo -e "${YELLOW}⚠ .git already exists. Remove it first if you want to re-init.${NC}"
  exit 1
fi

echo -e "${GREEN}==> git init${NC}"
git init

# ── .gitignore ─────────────────────────────────────────────
if [ ! -f ".gitignore" ]; then
  echo -e "${GREEN}==> Creating .gitignore${NC}"
  cat > .gitignore << 'GITIGNORE'
node_modules
.DS_Store
dist
coverage
.env
*.log
.idea
.vscode/*
.vscode/extensions.json
*.suo
*.lock

# AI tool runtime directories
.agents/
.claude/
.omx/
.docs/task/

# Binary / screenshot files
*.png
*.bmp
*.jpg
*.jpeg

# Python bytecode
__pycache__/
*.pyc
logs

# Agent / tool state
.swarm/
.omc

# Session-scoped state files
.claude-impl-state.md
.claude-progress.md
.claude-recovery.md
.test-progress.md
.squash-tmp/
.git.*-backup

# ── CUSTOMIZE: add project‑specific ignore patterns below ──
# /参考/
# /借鉴资料/
# data/
# credentials.json
GITIGNORE
fi

# ── Count files that would be committed ────────────────────
echo -e "${GREEN}==> Checking file count${NC}"
count=$(git ls-files --others --exclude-standard 2>/dev/null | wc -l)
if [ "$count" -gt 500 ]; then
  echo -e "${RED}⚠ ${count} files will be added to the initial commit.${NC}"
  echo -e "${RED}  This is TOO MANY. Review .gitignore and prune first.${NC}"
  echo -e "${RED}  Afterwards:  git add . && git commit -m 'chore: initial commit'${NC}"
  exit 1
fi

# ── First commit ───────────────────────────────────────────
echo -e "${GREEN}==> Creating initial commit${NC}"
git add .
git commit -m "chore: initial commit"

# ── Reminder: AGENTS.md git rules ──────────────────────────
echo ""
echo -e "${GREEN}✔ Git initialized successfully.${NC}"
echo ""
echo -e "${YELLOW}Next steps — copy these into AGENTS.md:${NC}"
echo "───────────────────────────────────────────"
echo '### Git 工作流'
echo ''
echo '- **禁止自动提交** — 修改文件后不要自动 `git add && git commit`。让变更留在工作区'
echo '  让 OpenCode 显示待处理变更。'
echo '- **仅当用户明确要求时才提交** — 用户说"提交"或"commit"时才执行 git add + git commit。'
echo '- **仅在用户明确要求时才推送** — 用户说"推送"或"push"时才执行 git push。'
echo '- 如果用户说"撤消"或"回退"，使用 git checkout -- <file> 或 git restore <file>'
echo '   撤销工作区变更。'
echo '- 如果用户说"暂存"或"stash"，使用 git stash push -u 暂存当前变更。'
echo "───────────────────────────────────────────"
