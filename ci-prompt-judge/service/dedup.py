"""话术去重算法（PRD 十六，联网更新必备）。

判定标准：
- 精准去重（100% 一致）：文本完全相同直接过滤
- 高相似度去重（阈值 85%）：语义/句式/表意相似度 >= 阈值判定重复
- 短话术强校验（<=20 字）：提升严格度，避免微改重复
- 长话术弱校验（>50 字）：适当放宽，保留差异化创新

相似度：字符级序列相似度（difflib）作为轻量可解释实现；
语义级可后续接入 embedding（预留接口）。
"""
from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List


def _clean(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def similarity(a: str, b: str) -> float:
    """字符序列相似度 0–1。"""
    ca, cb = _clean(a), _clean(b)
    if not ca or not cb:
        return 0.0
    return difflib.SequenceMatcher(None, ca, cb).ratio()


def is_duplicate(new_text: str, base_texts: List[str], cfg: Dict[str, Any]) -> bool:
    """判断 new_text 是否相对基准库重复。"""
    threshold = cfg.get("threshold", 0.85)
    short_len = cfg.get("short_strict_len", 20)
    long_len = cfg.get("long_relax_len", 50)
    n = len(new_text.strip())

    # 短话术强校验：阈值上浮；长话术弱校验：阈值下浮
    eff = threshold
    if n <= short_len:
        eff = min(0.98, threshold + 0.08)
    elif n > long_len:
        eff = max(0.5, threshold - 0.10)

    for base in base_texts:
        if _clean(new_text) == _clean(base):
            return True  # 精准去重
        if similarity(new_text, base) >= eff:
            return True  # 高相似去重
    return False


def filter_duplicates(new_texts: List[str], base_texts: List[str],
                      cfg: Dict[str, Any]) -> List[str]:
    """从候选中剔除与基准重复/同质化内容，返回全新话术。"""
    result: List[str] = []
    seen = list(base_texts)
    for t in new_texts:
        if not t or not t.strip():
            continue
        if is_duplicate(t, seen, cfg):
            continue
        result.append(t)
        seen.append(t)  # 同批次内也互查
    return result
