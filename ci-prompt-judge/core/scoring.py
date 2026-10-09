"""标准化提示词完整性评分（PRD 一、十七、二十一）。

四维加权：意图 30% / 特异性 25% / 结构 25% / 鲁棒性 20%（默认权重，可配置）。
- 短文本低分惩罚：超短且非白名单时软上限压低（PRD 短句易敷衍）
- 白名单豁免：专业极简指令（代码/CLI 等）取消惩罚并拉高基础分（PRD 十七）
输出 1–10 分（保留 1 位小数）。
"""
from __future__ import annotations

import re
from typing import Any, Dict

from core.rules_matcher import _count_structure_signals

_DIM_WEIGHT_DEFAULT = {
    "intent": 0.30,
    "specificity": 0.25,
    "structure": 0.25,
    "robustness": 0.20,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_dimensions(prompt: str, rules: Dict[str, Any], cfg: Dict[str, Any],
                     whitelist_hit: bool) -> Dict[str, float]:
    kw = rules.get("scoring_rules", {}).get("dimension_keywords", {})
    text = prompt.strip()
    n = len(text)

    # 意图清晰度：有清晰诉求即给出较高基础分，避免正常请求被打压
    intent_hits = sum(1 for k in kw.get("intent", []) if k in text)
    intent = 0.6 if n > 0 else 0.15
    intent += min(0.35, 0.12 * intent_hits)
    if n >= 8:
        intent += 0.1
    intent = _clamp01(intent)

    # 特异性（约束/细节/参数）
    spec_hits = sum(1 for k in kw.get("specificity", []) if k in text)
    spec = 0.4
    spec += min(0.5, 0.1 * spec_hits)
    if re.search(r"\d", text):
        spec += 0.1
    if n >= 25:
        spec += 0.1
    if whitelist_hit and n < 15:
        spec += 0.3  # 专业极简指令视为精准
    spec = _clamp01(spec)

    # 结构：存在任何结构化特征即给出基础分，分段/编号/列表显著提升
    sig = _count_structure_signals(text)
    structure = max(0.15, min(1.0, 0.15 + 0.18 * sig))
    if re.search(r"[：:、，,。；;]", text):
        structure = min(1.0, structure + 0.1)
    structure = _clamp01(structure)

    # 鲁棒性（上下文/受众/输入输出明确）
    rob_hits = sum(1 for k in kw.get("robustness", []) if k in text)
    robustness = 0.45
    robustness += min(0.4, 0.1 * rob_hits)
    robustness += min(0.15, n / 1500.0)
    robustness = _clamp01(robustness)

    return {
        "intent": round(intent, 3),
        "specificity": round(spec, 3),
        "structure": round(structure, 3),
        "robustness": round(robustness, 3),
    }


def compute_score(prompt: str, rules: Dict[str, Any], cfg: Dict[str, Any],
                  whitelist_hit: bool, is_short: bool) -> Dict[str, Any]:
    dims = score_dimensions(prompt, rules, cfg, whitelist_hit)
    weights = cfg.get("scoring", {}).get("weights", _DIM_WEIGHT_DEFAULT)
    raw = (
        dims["intent"] * weights.get("intent", 0.30)
        + dims["specificity"] * weights.get("specificity", 0.25)
        + dims["structure"] * weights.get("structure", 0.25)
        + dims["robustness"] * weights.get("robustness", 0.20)
    )
    score = raw * 10.0

    # 白名单豁免：取消短文本低分惩罚，基础分拉高
    wl_floor = cfg.get("scoring", {}).get("whitelist_floor", 7.0)
    short_penalty = cfg.get("scoring", {}).get("short_penalty_enabled", True)

    short_penalized = False
    if whitelist_hit:
        score = max(score, wl_floor)
    elif short_penalty and is_short:
        soft_cap = rules.get("scoring_rules", {}).get("short_penalty_rules", {}).get("R01_soft_cap", 4.0)
        if score > soft_cap:
            score = soft_cap
        short_penalized = True

    score = max(1.0, min(10.0, score))
    return {
        "score": round(score, 1),
        "dimensions": dims,
        "whitelist_hit": whitelist_hit,
        "short_penalized": short_penalized,
    }


def describe_dimensions(dims: Dict[str, float]) -> str:
    return (
        f"意图{int(dims['intent']*100)}% "
        f"特异性{int(dims['specificity']*100)}% "
        f"结构{int(dims['structure']*100)}% "
        f"鲁棒性{int(dims['robustness']*100)}%"
    )
