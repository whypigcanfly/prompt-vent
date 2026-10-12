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
# 且常规安装不依赖源码目录存活，对终端用户更健壮。
# 加 --upgrade：PATH 上可能残留旧版 ci-pj（issue #9），确保本机注册的是新版
$PIP install --upgrade "$SRC_DIR" --quiet && echo "ci-pj 安装完成 ✅" || {
  if [ "$MODE" = "local" ]; then
    echo "安装失败，请手动执行：pip install --upgrade $SRC_DIR" >&2
  else
    echo "安装失败，请手动执行：pip install --upgrade git+$REPO_URL#subdirectory=$PKG_SUBDIR" >&2
  fi
  exit 1
}

# 定位刚安装的 ci-pj 可执行。
# 优先级：① pip 同 bin 目录 ② Python user-site bin（pip --user 安装落点，常不在 PATH，
# issue #9：此目录里的新版被旧版残留遮蔽） ③ PATH 上的 ci-pj（可能为旧版残留，仅兜底）
find_ci_pj() {
  local cand
  local pip_bin
  pip_bin="$(command -v "${PIP%% *}" 2>/dev/null || true)"
  if [ -n "$pip_bin" ] && [ -x "$(dirname "$pip_bin")/ci-pj" ]; then
    dirname "$pip_bin"
    return 0
  fi
  cand="$(python3 -m site --user-base 2>/dev/null)/bin"
  if [ -x "$cand/ci-pj" ]; then
    echo "$cand"
    return 0
  fi
  cand="$(command -v ci-pj 2>/dev/null || true)"
  if [ -n "$cand" ]; then
    dirname "$cand"
    return 0
  fi
  return 1
}

# 解析真实路径（readlink -f 不可用时退回原始路径，仅用于比较）
realpath_or_raw() {
  local p
  p="$(readlink -f "$1" 2>/dev/null || true)"
  echo "${p:-$1}"
}

PJ_BIN_DIR=""
if PJ_BIN_DIR="$(find_ci_pj)"; then
  CI_PJ_BIN="$PJ_BIN_DIR/ci-pj"
  # PATH 上另有别的 ci-pj（旧版残留）→ 显式警告，避免用户误用旧逻辑
  # （PATH 解析结果可能是软链，先解析真实路径再比较，避免把新软链误判为旧版）
  PATH_PJ="$(command -v ci-pj 2>/dev/null || true)"
  if [ -n "${PATH_PJ}" ] && [ "$(realpath_or_raw "$PATH_PJ")" != "$(realpath_or_raw "$CI_PJ_BIN")" ]; then
    echo "⚠️  PATH 上的 ci-pj (${PATH_PJ}) 为旧版残留，本次安装将使用新版：${CI_PJ_BIN}" >&2
    echo "    建议清理旧版避免混淆：rm ${PATH_PJ}" >&2
  fi
else
  CI_PJ_BIN=""
fi
if [ -z "$CI_PJ_BIN" ]; then
  echo "未找到 ci-pj 可执行文件，请检查 pip 安装日志。" >&2
  exit 1
fi

echo "ci-pj 版本：$("$CI_PJ_BIN" --version 2>/dev/null || echo '未知（旧版无 --version，说明 PATH 上是旧残留，请按上方提示清理）')"

# ---------- 2.5) 保证 ci-pj 命令在 PATH 上可用（issue #13）----------
# pip --user 安装会把 ci-pj 落在 user-site bin（如 ~/Library/Python/3.9/bin），
# 该目录默认不在 PATH，终端会报 command not found。
# 方案A：软链到几乎总在 PATH 上的 ~/.local/bin；若该目录也不在 PATH 则给出明确提示。
LOCAL_BIN="$HOME/.local/bin"
RESOLVED_PJ="$(command -v ci-pj 2>/dev/null || true)"
if [ "$(realpath_or_raw "${RESOLVED_PJ:-/nonexistent}")" != "$(realpath_or_raw "$CI_PJ_BIN")" ]; then
  mkdir -p "$LOCAL_BIN"
  LINK="$LOCAL_BIN/ci-pj"
  if [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
    OLD_BAK="$LINK.bak-$(date +%Y%m%d%H%M%S)"
    mv "$LINK" "$OLD_BAK"
    echo "检测到 $LINK 为旧版残留（非软链），已备份为：$OLD_BAK"
  fi
  ln -sfn "$CI_PJ_BIN" "$LINK"
  echo "已创建软链：$LINK -> $CI_PJ_BIN"
  RESOLVED_PJ="$(command -v ci-pj 2>/dev/null || true)"
fi
if [ "$(realpath_or_raw "${RESOLVED_PJ:-/nonexistent}")" != "$(realpath_or_raw "$CI_PJ_BIN")" ]; then
  case ":$PATH:" in
    *":$LOCAL_BIN:"*)
      echo "⚠️  新终端里 ci-pj 仍指向 ${RESOLVED_PJ:-无}，可能被 PATH 上更靠前的旧版遮蔽，请清理旧版。" >&2 ;;
    *)
      echo "⚠️  $LOCAL_BIN 不在 PATH，请将下面一行加入 ~/.zshrc（或 ~/.bashrc）后重开终端：" >&2
      echo '    export PATH="$HOME/.local/bin:$PATH"' >&2 ;;
  esac
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
echo "若当前终端提示 command not found，执行 rehash（zsh）或重开终端即可。"
echo "试试：ci-pj status"
echo "切换人设：ci-pj mode 渣女"
echo "评判一段：ci-pj run \"帮我写一封辞职信，语气要体面\""
