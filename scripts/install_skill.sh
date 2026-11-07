#!/bin/bash
# AIエージェントの skills へ SKILL.md / skill.yaml を配置する。
# 使い方: bash scripts/install_skill.sh [muse|gemini|<配置先パス>]
#   muse       -> $HOME/workspace/custom-skills/film-date-agent (Muse、既定)
#   gemini     -> $HOME/.gemini/config/skills/film-date-agent (Gemini CLI / Antigravity)
#   antigravity -> gemini と同じ
#   <パス>     -> そのディレクトリへそのまま配置する (従来互換)
# 環境変数 FILM_DATE_SKILL_DEST でも指定できる (引数が優先、無指定時の既定は muse)。
set -euo pipefail

TARGET="${1:-${FILM_DATE_SKILL_DEST:-muse}}"
case "$TARGET" in
  muse) DEST="$HOME/workspace/custom-skills/film-date-agent" ;;
  gemini|antigravity) DEST="$HOME/.gemini/config/skills/film-date-agent" ;;
  *) DEST="$TARGET" ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DEST"
cp "$REPO_ROOT/skill/SKILL.md" "$DEST/SKILL.md"
echo "installed: $DEST/SKILL.md"
if [ -f "$REPO_ROOT/skill/skill.yaml" ]; then
  cp "$REPO_ROOT/skill/skill.yaml" "$DEST/skill.yaml"
  echo "installed: $DEST/skill.yaml"
fi
