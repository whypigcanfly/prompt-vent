"""联网话术增量更新（PRD 11.7，手动触发、增量追加、去重降噪）。

设计要点：
- 纯增量追加：原生预制话术永久保留，零丢失、零覆盖（PRD 11.1.1）
- 仅用户手动指令触发，无自动定时（PRD 硬性约束）
- 去重校验后入库，标记来源标签「联网更新」
- 单日上限、超时重试（PRD 十九）

重要：CLI 自身无联网能力。真实联网检索依赖宿主 Agent 的 WebSearch。
本模块暴露可插拔 fetcher 接口：宿主把「检索到的新话术列表」喂进来即可。
未提供 fetcher 时，输出友好提示并给出检索词建议，不破坏存量。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import core.pathutil as pathutil
from core import loader
from service import dedup as dedup_mod
from storage.store import StateStore


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _load_user_speech() -> Dict[str, Any]:
    p = Path(os.path.expanduser(pathutil.default_user_speech_path()))
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"personas": {}}


def _save_user_speech(data: Dict[str, Any]) -> None:
    p = Path(os.path.expanduser(pathutil.default_user_speech_path()))
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_base_texts(persona_name: str) -> List[str]:
    """以原生 + 已有用户话术作为去重基准库。"""
    personas = loader.load_personas()
    base: List[str] = []
    p = personas.get("personas", {}).get(persona_name, {})
    for pool in p.get("rule_speeches", {}).values():
        base.extend(it.get("text", "") for it in pool)
    base.extend(it.get("text", "") for it in p.get("fallback", []))
    user = _load_user_speech().get("personas", {}).get(persona_name, {})
    for pool in user.get("rule_speeches", {}).values():
        base.extend(it.get("text", "") for it in pool)
    base.extend(it.get("text", "") for it in user.get("fallback", []))
    return [b for b in base if b]


def _check_daily_limit(store: StateStore, cfg: Dict[str, Any]) -> bool:
    rec = store.get("update_counts", {})
    if rec.get("date") != _today():
        return True
    return rec.get("count", 0) < cfg.get("update", {}).get("max_per_day", 10)


def _inc_daily(store: StateStore) -> None:
    rec = store.get("update_counts", {})
    if rec.get("date") != _today():
        rec = {"date": _today(), "count": 0}
    rec["count"] = rec.get("count", 0) + 1
    store.set("update_counts", rec)


# 默认检索建议词（供宿主 WebSearch 使用 / 给用户提示）
SUGGEST_KEYWORDS = {
    "渣女": ["傲娇 吐槽 语气 短句", "恋爱 拉扯 文案 搞笑", "阴阳怪气 可爱 台词"],
    "激励师": ["温柔 鼓励 文案 短句", "治愈 正能量 暖心 台词", "鼓励 学习 工作 话语"],
    "贴吧老哥": ["贴吧 老哥 语气 梗", "接地气 吐槽 短句", "网络热梗 口语 台词"],
    "腹黑毒舌女": ["腹黑 毒舌 台词 语录", "阴阳怪气 嘲讽 文案", "毒舌 女王 怼人 短句"],
}


def update_persona(persona_name: str,
                   fetcher: Optional[Callable[[str, int], List[str]]] = None,
                   cfg: Optional[Dict[str, Any]] = None,
                   store: Optional[StateStore] = None,
                   logger=None) -> Dict[str, Any]:
    cfg = cfg or loader.load_config()
    store = store or StateStore()
    dedup_cfg = cfg.get("dedup", {})
    max_per = cfg.get("update", {}).get("max_per_update", 20)

    if not _check_daily_limit(store, cfg):
        return {"ok": False, "reason": "单日更新次数已用尽", "added": 0, "total": 0}

    base = _build_base_texts(persona_name)
    if fetcher is None:
        suggestions = SUGGEST_KEYWORDS.get(persona_name, ["网络热梗 趣味 台词"])
        return {
            "ok": False,
            "reason": "未提供联网检索器（fetcher）。请在支持 WebSearch 的宿主 Agent 中运行 /pj-update。",
            "suggestions": suggestions,
            "added": 0,
            "total": len(base),
        }

    try:
        raw = fetcher(persona_name, max_per) or []
    except Exception as e:
        if logger:
            logger.error("update", f"联网更新失败: {e}", persona=persona_name)
        return {"ok": False, "reason": f"联网检索异常: {e}", "added": 0, "total": len(base)}

    cleaned = [t.strip() for t in raw if isinstance(t, str) and t.strip()]
    added = dedup_mod.filter_duplicates(cleaned, base, dedup_cfg)

    # 增量追加到用户话术（标记来源）
    user = _load_user_speech()
    p = user.setdefault("personas", {}).setdefault(persona_name, {})
    p.setdefault("fallback", [])
    existing_texts = {it.get("text") for it in p["fallback"]}
    for t in added:
        if t in existing_texts:
            continue
        p["fallback"].append({"text": t, "weight": 1, "source": "联网更新"})
    _save_user_speech(user)
    _inc_daily(store)
    if logger:
        logger.info("update", f"角色 {persona_name} 新增 {len(added)} 条话术",
                    persona=persona_name, added=len(added))
    return {
        "ok": True,
        "persona": persona_name,
        "added": len(added),
        "total": len(_build_base_texts(persona_name)),
        "rejected": len(cleaned) - len(added),
    }
