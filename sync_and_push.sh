#!/usr/bin/env bash
# wowland-ops-mirror 一键同步推送脚本
# 用法: ./sync_and_push.sh
# 依赖: GITHUB_TOKEN 环境变量 或 ~/.github_token 文件(仅含 token)
set -euo pipefail
cd "$(dirname "$0")"

REPO_URL="https://github.com/horton2048/wowland-ops-mirror.git"
GIT_REMOTE="origin"
GIT_BRANCH="main"

# 获取 token: 环境变量优先, 其次 ~/.github_token
TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f "$HOME/.github_token" ]; then
    TOKEN="$(tr -d '\r\n' < "$HOME/.github_token")"
fi
if [ -z "$TOKEN" ]; then
    echo "[FAIL] 未找到 GitHub token (设置 GITHUB_TOKEN 或写入 ~/.github_token)" >&2
    exit 1
fi

echo "[1/3] 同步飞书文档..."
python3 sync_wowland.py

echo "[2/3] 提交变更..."
# 忽略 README/.sync_manifest.json 的时间戳噪音, 仅当文档或资源内容变化时才提交
CHANGED="$(git status --porcelain | grep -vE '^.. (README\.md|\.sync_manifest\.json)$' || true)"
if [ -z "$CHANGED" ]; then
    echo "      无内容变更, 跳过提交"
    git checkout -- README.md .sync_manifest.json 2>/dev/null || true
else
    git add -A
    git commit -m "sync: $(date '+%Y-%m-%d %H:%M:%S') from Feishu wiki" >/dev/null 2>&1 || true
fi

echo "[3/3] 推送 GitHub..."
# 使用 token 鉴权的 push URL(避免 token 写入 remote 配置)
git push "https://x-access-token:${TOKEN}@github.com/horton2048/wowland-ops-mirror.git" "HEAD:${GIT_BRANCH}" 2>&1 | grep -vE "^remote: (Resolving|Checking)" || true
echo "[OK] 同步完成: $(date '+%Y-%m-%d %H:%M:%S')"
