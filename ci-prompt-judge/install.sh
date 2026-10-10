#!/usr/bin/env bash
# 词趣判官 一键安装器（issue #1：一个命令自动安装 + 自动配置钩子）
#
# 用法：
#   bash install.sh                     # 交互式选择 Agent（需在本目录或已 clone 仓库）
#   bash install.sh claude_code         # 非交互，安装指定 Agent 适配（含自动注册钩子）
#   bash install.sh claude_code codex   # 可同时指定多个
#
# 无需 clone 的一行安装（curl 直装，自动从 GitHub 拉取源码包）：
#   curl -fsSL https://raw.githubusercontent.com/whypigcanfly/prompt-vent/main/ci-prompt-judge/install.sh | bash -s -- claude_code
set -euo pipefail

REPO_URL="https://github.com/whypigcanfly/prompt-vent.git"
REPO_TARBALL="https://github.com/whypigcanfly/prompt-vent/archive/refs/heads/main.tar.gz"
PKG_SUBDIR="ci-prompt-judge"
KNOWN_AGENTS="claude_code codex hermes workbuddy"

echo "== 词趣判官 ci-prompt-judge 安装 =="

# ---------- 1) 定位包源码目录 ----------
# 当前目录就是包目录（含 pyproject.toml + main.py）→ 直接安装
# 否则 → 从 GitHub 下载 tarball 解出包子目录，临时目录内安装
TMP_DIR=""
MODE="local"
if [ -f "pyproject.toml" ] && [ -f "main.py" ]; then
  SRC_DIR="$(pwd)"
else
  MODE="remote"
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  echo "当前目录不是包源码目录，从 GitHub 拉取源码包..."
  TARBALL="$TMP_DIR/repo.tar.gz"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$REPO_TARBALL" -o "$TARBALL"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TARBALL" "$REPO_TARBALL"
  else
    echo "未找到 curl/wget，无法下载源码包。" >&2
    exit 1
  fi
  mkdir -p "$TMP_DIR/repo"
  tar -xzf "$TARBALL" -C "$TMP_DIR/repo" --strip-components=1
  SRC_DIR="$TMP_DIR/repo/$PKG_SUBDIR"
  if [ ! -f "$SRC_DIR/pyproject.toml" ]; then
    echo "源码包解压异常：未找到 $PKG_SUBDIR/pyproject.toml" >&2
    exit 1
  fi
fi

# ---------- 2) 安装 Python 包（提供 ci-pj 命令）----------
PIP=""
for c in pip pip3; do
  if command -v "$c" >/dev/null 2>&1; then PIP="$c"; break; fi
done
if [ -z "$PIP" ] && command -v uv >/dev/null 2>&1; then
  PIP="uv pip"
fi
if [ -z "$PIP" ]; then
  echo "未找到 pip/pip3/uv，请先安装 Python 3.8+ 与 pip。" >&2
  exit 1
fi

echo "正在安装 ci-pj 命令行工具 (来源: ${MODE})..."
# 统一用常规安装（不用 -e）：老版本 pip（<21.3）不支持 PEP 660 可编辑安装，
# 且常规安装不依赖源码目录存活，对终端用户更健壮
$PIP install "$SRC_DIR" --quiet && echo "ci-pj 安装完成 ✅" || {
  if [ "$MODE" = "local" ]; then
    echo "安装失败，请手动执行：pip install $SRC_DIR" >&2
  else
    echo "安装失败，请手动执行：pip install git+$REPO_URL#subdirectory=$PKG_SUBDIR" >&2
  fi
  exit 1
}

# 定位 ci-pj 可执行（与 pip 同 bin 目录优先）
CI_PJ_BIN="$(command -v ci-pj 2>/dev/null || true)"
if [ -z "$CI_PJ_BIN" ]; then
  PIP_BIN="$(command -v "${PIP%% *}" 2>/dev/null || true)"
  if [ -n "$PIP_BIN" ] && [ -x "$(dirname "$PIP_BIN")/ci-pj" ]; then
    CI_PJ_BIN="$(dirname "$PIP_BIN")/ci-pj"
  fi
fi
if [ -z "$CI_PJ_BIN" ]; then
  echo "未找到 ci-pj 可执行文件，请检查 pip 安装日志。" >&2
  exit 1
fi

# ---------- 3) 确定要适配的 Agent ----------
TARGETS=()
if [ $# -gt 0 ]; then
  for a in "$@"; do
    case " $KNOWN_AGENTS " in
      *" $a "*) TARGETS+=("$a") ;;
      *) echo "未知 Agent: $a (支持: ${KNOWN_AGENTS})" >&2; exit 1 ;;
    esac
  done
elif [ -t 0 ]; then
  # 交互式菜单（仅终端直跑时）
  echo
  echo "请选择要适配的 Agent（可多选，逗号分隔，或 all）："
  echo "  1) claude_code   2) codex   3) hermes   4) workbuddy"
  read -r -p "输入编号或名称（默认 all）：" CHOICE
  CHOICE="${CHOICE:-all}"
  declare -A MAP=( [1]=claude_code [2]=codex [3]=hermes [4]=workbuddy )
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
else
  echo "非交互环境且未指定 Agent。用法：install.sh <agent>（支持：$KNOWN_AGENTS）" >&2
  exit 1
fi

# ---------- 4) 生成适配文件 + 自动注册钩子 ----------
for t in "${TARGETS[@]}"; do
  echo
  "$CI_PJ_BIN" install "$t" || echo "适配 $t 生成失败，请手动处理。"
done

echo
echo "== 安装完成 =="
echo "试试：ci-pj status"
echo "切换人设：ci-pj mode 渣女"
echo "评判一段：ci-pj run \"帮我写一封辞职信，语气要体面\""
