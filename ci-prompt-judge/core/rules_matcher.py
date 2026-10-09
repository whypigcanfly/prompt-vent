"""特征规则匹配器（PRD 五、十五）。

支持触发条件类型：length / keyword / structure / regex。
多规则命中按权重降序、ID 升序排序（PRD 15.1 权重优先原则）。
白名单检测（PRD 十七）单独提供，供评分层豁免短文本低分惩罚。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _count_structure_signals(text: str) -> int:
    sig = 0
    if text.count("\n") >= 2:
        sig += 1
    if re.search(r"(^|\n)\s*[-*]\s+", text):
        sig += 1
    if re.search(r"(^|\n)\s*(\d+[.、]|[一二三四五六七八九十]+[、.])", text):
        sig += 1
    # 中文序号/分段：第一段、第二点、第三条等
    if re.search(r"第[一二三四五六七八九十百千0-9]+[段条点章节部分句]", text):
        sig += 1
    if re.search(r"(一是|二是|三是|首先|其次|最后|其一|其二)", text):
        sig += 1
    if "```" in text:
        sig += 1
    for kw in ("格式", "结构", "步骤", "要求", "约束", "以下", "如下", "分成", "必须",
               "分段", "分点", "列", "分别", "例如", "比如"):
        if kw in text:
            sig += 1
    return sig


def match_rules(prompt: str, rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    """返回所有命中的已启用规则，按 (weight desc, id asc) 排序。"""
    matched: List[Dict[str, Any]] = []
    for rule in rules.get("feature_rules", []):
        if rule.get("status", "enabled") != "enabled":
            continue
        if _rule_hit(prompt, rule):
            matched.append(rule)
    # 权重优先，权重相同按 ID 升序
    matched.sort(key=lambda r: (-int(r.get("weight", 0)), r.get("id", "")))
    return matched


def _rule_hit(prompt: str, rule: Dict[str, Any]) -> bool:
    rtype = rule.get("type")
    if rtype == "length":
        n = len(prompt.strip())
        op, val = rule.get("op"), rule.get("value")
        if op == "<=":
            return n <= val
        if op == ">":
            return n > val
        if op == ">=":
            return n >= val
        if op == "<":
            return n < val
        return False
    if rtype == "keyword":
        kws = rule.get("keywords", [])
        return any(kw in prompt for kw in kws)
    if rtype == "structure":
        # R08 结构化：结构信号 >= 3 判定为结构化提示词
        return _count_structure_signals(prompt) >= 3
    if rtype == "regex":
        pat = rule.get("pattern")
        if pat:
            return re.search(pat, prompt) is not None
    return False


def detect_whitelist(prompt: str, rules: Dict[str, Any]) -> bool:
    """专业场景白名单命中（PRD 十七）。命中则豁免短文本低分惩罚。"""
    wl = rules.get("whitelist", {})
    if not wl.get("enabled", False):
        return False
    low = prompt.lower()
    for kw in wl.get("keywords", []):
        if kw.lower() in low:
            return True
    for pat in wl.get("regex", []):
        if re.search(pat, prompt):
            return True
    return False


def top_rule(matched: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """冲突解决：取权重最高者（已排序）。"""
    return matched[0] if matched else None


def describe_matches(matched: List[Dict[str, Any]]) -> str:
    return "、".join(f"{r.get('id')}({r.get('name')})" for r in matched) or "无"
