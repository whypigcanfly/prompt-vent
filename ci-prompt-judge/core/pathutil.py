"""路径与资源定位工具。

同时支持三种运行形态：
1. 作为已安装包运行（pip install 后，资源随 core.data 包发布）
2. 作为本地仓库直接运行（python main.py，资源在仓库根的 config/ rule/ speech/）
3. 开发者通过环境变量覆盖内置资源目录

资源定位优先级（按子目录 config / rule / speech 分别）：
  环境变量目录（CI_PJ_*_DIR） > 资源包 core.data > 仓库源码目录（兜底）

注意：REPO_ROOT 仅作为兜底路径使用；正常安装/可编辑安装都应命中「资源包 core.data」，
因此不再依赖把 core 包放在仓库根这一假设（这正是旧实现非可编辑安装失败的根因之一）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# 内置资源随此包发布（安装后位于 site-packages/core/data/...）
_DATA_PKG = "core.data"

ENV_CONFIG_DIR = "CI_PJ_CONFIG_DIR"
ENV_RULE_DIR = "CI_PJ_RULE_DIR"
ENV_SPEECH_DIR = "CI_PJ_SPEECH_DIR"

# 子目录名 -> 对应的环境变量名
_SUB_ENV = {
    "config": ENV_CONFIG_DIR,
    "rule": ENV_RULE_DIR,
    "speech": ENV_SPEECH_DIR,
}

# importlib.resources.files 在 Python 3.9+ 才提供；3.8 回退到仓库源码兜底
try:
    from importlib.resources import files as _irs_files  # type: ignore

    _HAS_IRS = True
except ImportError:  # pragma: no cover - Python < 3.9
    _HAS_IRS = False


def _repo_root() -> Path:
    # 本文件位于 core/pathutil.py -> core -> 仓库根
    return Path(__file__).resolve().parent.parent


def _read_env(sub: str, filename: str) -> Optional[str]:
    env = os.environ.get(_SUB_ENV[sub])
    if not env:
        return None
    p = Path(os.path.expanduser(env)) / filename
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return None


def _read_resource(sub: str, filename: str) -> Optional[str]:
    if not _HAS_IRS:
        return None
    try:
        ref = _irs_files(_DATA_PKG).joinpath(sub, filename)
    except (ModuleNotFoundError, TypeError, ValueError):
        return None
    try:
        # Traversable.read_text 在 3.9+ 可用
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, AttributeError):
        return None


def _read_legacy(sub: str, filename: str) -> Optional[str]:
    p = _repo_root() / sub / filename
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return None


def read_text(sub: str, filename: str) -> str:
    """按优先级读取内置资源文本，找不到抛 FileNotFoundError。"""
    for fn in (_read_env, _read_resource, _read_legacy):
        try:
            txt = fn(sub, filename)
        except Exception:
            txt = None
        if txt is not None:
            return txt
    raise FileNotFoundError(
        f"资源未找到：{sub}/{filename}（已尝试 环境变量目录 / 资源包 {_DATA_PKG} / 仓库源码目录）"
    )


# ---- 以下保留为兼容/调试接口：返回真实文件系统目录（若有），否则返回资源包 Traversable ----
def _resolve_dir(sub: str):
    env = os.environ.get(_SUB_ENV[sub])
    if env:
        return Path(os.path.expanduser(env))
    if _HAS_IRS:
        try:
            return _irs_files(_DATA_PKG).joinpath(sub)
        except (ModuleNotFoundError, TypeError, ValueError):
            pass
    return _repo_root() / sub


def config_dir():
    return _resolve_dir("config")


def rule_dir():
    return _resolve_dir("rule")


def speech_dir():
    return _resolve_dir("speech")


def default_state_path() -> str:
    return os.environ.get("CI_PJ_STATE_PATH", "~/.ci-pj/state.json")


def default_user_speech_path() -> str:
    return os.environ.get("CI_PJ_USER_SPEECH_PATH", "~/.ci-pj/speech.user.json")


def default_log_dir() -> str:
    return os.environ.get("CI_PJ_LOG_DIR", "~/.ci-pj/log")
