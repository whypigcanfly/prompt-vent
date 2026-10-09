"""话术渲染器（PRD 六、十五）。

渲染优先级（命中即优先，单规则多话术随机轮换）：
1. 权重最高命中规则的「规则绑定预制话术」中随机（按权重）
2. 否则从「通用兜底话术池」随机（按权重）
支持话术权重配置（热门话术展示概率更高）。
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional


def _weighted_pick(items: List[Dict[str, Any]]) -> Optional[str]:
    if not items:
        return None
    weights = [max(0.0, float(it.get("weight", 1))) for it in items]
    total = sum(weights)
    if total <= 0:
        return random.choice(items).get("text")
    chosen = random.choices(items, weights=weights, k=1)[0]
    return chosen.get("text")


def render(persona_name: str, matched_rules: List[Dict[str, Any]],
           personas: Dict[str, Any]) -> str:
    personas_map = personas.get("personas", {})
    persona = personas_map.get(persona_name)
    if not persona:
        # 人设未知时回退到第一个可用人设，保证不报错
        persona = next(iter(personas_map.values()), None)
        if not persona:
            return "（话术库为空）"

    rule_speeches = persona.get("rule_speeches", {})
    fallback = persona.get("fallback", [])

    # 优先：权重最高的命中规则，且该人设绑定了对应话术
    for rule in matched_rules:
        rid = rule.get("id")
        pool = rule_speeches.get(rid)
        if pool:
            text = _weighted_pick(pool)
            if text:
                return text

    # 兜底：通用话术池
    text = _weighted_pick(fallback)
    return text or "（暂无合适话术）"
