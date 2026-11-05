#!/bin/bash
# AIエージェントの custom-skills へ SKILL.md を配置する。
# 使い方: bash scripts/install_skill.sh [配置先ディレクトリ]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/workspace/custom-skills/film-date-agent}"
mkdir -p "$DEST"
cp "$REPO_ROOT/skill/SKILL.md" "$DEST/SKILL.md"
echo "installed: $DEST/SKILL.md"
if [ -f "$REPO_ROOT/skill/skill.yaml" ]; then
  cp "$REPO_ROOT/skill/skill.yaml" "$DEST/skill.yaml"
  echo "installed: $DEST/skill.yaml"
fi
