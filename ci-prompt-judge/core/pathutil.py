"""路径与资源定位工具。

同时支持两种运行形态：
1. 作为已安装包运行（pip install 后 import 路径）
2. 作为本地仓库直接运行（python main.py）

资源优先级：用户覆盖目录（~/.ci-pj/）> 仓库内置目录（config/ rule/ speech/）。
"""
from __future__ import annotations

import os
from pathlib import Path

# 仓库根 = 本文件的上两级（core/pathutil.py -> core -> root）
REPO_ROOT = Path(__file__).resolve().parent.parent

# 允许通过环境变量覆盖内置资源目录，方便开发者自定义
ENV_CONFIG_DIR = "CI_PJ_CONFIG_DIR"
ENV_RULE_DIR = "CI_PJ_RULE_DIR"
ENV_SPEECH_DIR = "CI_PJ_SPEECH_DIR"


def _resolve(env_var: str, fallback_sub: str) -> Path:
    env = os.environ.get(env_var)
    if env:
        return Path(os.path.expanduser(env))
    return REPO_ROOT / fallback_sub


def config_dir() -> Path:
    return _resolve(ENV_CONFIG_DIR, "config")


def rule_dir() -> Path:
    return _resolve(ENV_RULE_DIR, "rule")


def speech_dir() -> Path:
    return _resolve(ENV_SPEECH_DIR, "speech")


def default_state_path() -> str:
    return os.environ.get("CI_PJ_STATE_PATH", "~/.ci-pj/state.json")


def default_user_speech_path() -> str:
    return os.environ.get("CI_PJ_USER_SPEECH_PATH", "~/.ci-pj/speech.user.json")


def default_log_dir() -> str:
    return os.environ.get("CI_PJ_LOG_DIR", "~/.ci-pj/log")
