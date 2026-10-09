"""固定输出格式（PRD 八，强制统一不可乱改）。

关闭模式（off）：无任何输出，直接进入原对话逻辑。
常规模式：
【XX语气评判｜提示词完整性得分：X/10】评判话术内容
---放行提示词---
用户原始完整Prompt
"""
from __future__ import annotations

from typing import Optional


def format_output(mode: str, score: float, comment: str,
                  original_prompt: str) -> str:
    """生成标准化评判结果。mode 为当前人设（不含 off）。"""
    return (
        f"【{mode}语气评判｜提示词完整性得分：{score}/10】{comment}\n"
        f"---放行提示词---\n"
        f"{original_prompt}"
    )


def should_output(mode: str) -> bool:
    """off 模式不输出任何内容。"""
    return mode != "off"
