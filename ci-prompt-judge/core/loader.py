"""配置/规则/话术加载器（带缓存 + 用户覆盖合并）。

加载策略：
- 内置默认配置 config/config.default.json
- 用户覆盖：~/.ci-pj/config.user.json（可选，深度合并）
- 规则 rule/rules.json + 用户规则覆盖 rule/rules.user.json
- 话术 speech/personas.json + 用户话术 speech.user.json（合并追加）
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from core import pathutil


def _load_json(path) -> Dict[str, Any]:
    p = Path(os.path.expanduser(str(path)))
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _deep_merge(base: Dict, override: Dict) -> Dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@lru_cache(maxsize=16)
def load_config() -> Dict[str, Any]:
    cfg = json.loads(pathutil.read_text("config", "config.default.json"))
    user = _load_json(os.path.expanduser("~/.ci-pj/config.user.json"))
    return _deep_merge(cfg, user)


@lru_cache(maxsize=16)
def load_rules() -> Dict[str, Any]:
    rules = json.loads(pathutil.read_text("rule", "rules.json"))
    user = _load_json(os.path.expanduser("~/.ci-pj/rules.user.json"))
    # 用户规则按 id 合并覆盖
    if "feature_rules" in user:
        by_id = {r["id"]: r for r in rules.get("feature_rules", [])}
        for r in user["feature_rules"]:
            by_id[r["id"]] = {**by_id.get(r["id"], {}), **r}
        rules["feature_rules"] = list(by_id.values())
    for key in ("scoring_rules", "whitelist", "conflict_resolution"):
        if key in user:
            rules[key] = _deep_merge(rules.get(key, {}), user[key])
    return rules


@lru_cache(maxsize=16)
def load_personas() -> Dict[str, Any]:
    base = json.loads(pathutil.read_text("speech", "personas.json"))
    user_path = os.path.expanduser(pathutil.default_user_speech_path())
    user = _load_json(user_path)
    if not user:
        return base
    # 用户话术按 persona -> rule_speeches / fallback 追加
    for name, persona in user.get("personas", {}).items():
        if name not in base.get("personas", {}):
            base.setdefault("personas", {})[name] = persona
            continue
        tgt = base["personas"][name]
        for rk, lines in persona.get("rule_speeches", {}).items():
            tgt.setdefault("rule_speeches", {}).setdefault(rk, []).extend(lines)
        if "fallback" in persona:
            tgt.setdefault("fallback", []).extend(persona["fallback"])
    return base
