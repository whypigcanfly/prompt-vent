#!/usr/bin/env bash
# 词趣判官 一键安装器
# 用法：bash install.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "== 词趣判官 ci-prompt-judge 安装 =="

# 1) 安装 Python 包（提供 ci-pj 命令）
if command -v pip >/dev/null 2>&1; then
  PIP=pip
elif command -v pip3 >/dev/null 2>&1; then
  PIP=pip3
else
  echo "未找到 pip，请先安装 Python 3.8+。" >&2
  exit 1
fi

echo "正在安装 ci-pj 命令行工具..."
$PIP install -e . --quiet && echo "ci-pj 安装完成 ✅" || {
  echo "安装失败，请手动执行：pip install -e ." >&2
  exit 1
}

# 2) 选择目标 Agent 生成适配文件
echo
echo "请选择要适配的 Agent（可多选，逗号分隔，或 all）："
echo "  1) claude_code   2) codex   3) hermes   4) workbuddy"
read -r -p "输入编号或名称（默认 all）：" CHOICE
CHOICE="${CHOICE:-all}"

declare -A MAP=( [1]=claude_code [2]=codex [3]=hermes [4]=workbuddy )
TARGETS=()
if [ "$CHOICE" = "all" ]; then
  TARGETS=(claude_code codex hermes workbuddy)
else
  IFS=',' read -ra PARTS <<< "$CHOICE"
  for p in "${PARTS[@]}"; do
    p="$(echo -n "$p" | tr -d '[:space:]')"
    if [[ "$p" =~ ^[0-9]$ ]]; then p="${MAP[$p]:-}"; fi
    [ -n "$p" ] && TARGETS+=("$p")
  done
fi

for t in "${TARGETS[@]}"; do
  echo
  ci-pj install "$t" || echo "适配 $t 生成失败，请手动处理。"
done

echo
echo "== 安装完成 =="
echo "试试：ci-pj status"
echo "切换人设：ci-pj mode 渣女"
echo "评判一段：ci-pj run \"帮我写一封辞职信，语气要体面\""
