"""安装分发器（PRD 十一 多 Agent 适配）。

`ci-pj install <agent>` 调用对应适配器，生成该平台的命令文件 / 技能文件 / 钩子片段，
并打印安装说明。支持：claude_code、codex、hermes、workbuddy。
"""
from __future__ import annotations

import sys
from typing import Dict

from adapter.base import AgentAdapter

_REGISTRY: Dict[str, str] = {
    "claude_code": "adapter.claude_code:ClaudeCodeAdapter",
    "codex": "adapter.codex:CodexAdapter",
    "hermes": "adapter.hermes:HermesAdapter",
    "workbuddy": "adapter.workbuddy:WorkBuddyAdapter",
}


def _resolve(agent: str) -> AgentAdapter:
    spec = _REGISTRY.get(agent)
    if not spec:
        raise ValueError(f"未知 Agent：{agent}。支持：{', '.join(_REGISTRY)}")
    module_path, cls_name = spec.split(":")
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, cls_name)()


def install(agent: str, target_dir: str | None = None) -> int:
    try:
        adapter = _resolve(agent)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    created, notes = adapter.generate(target_dir)
    print(f"== 词趣判官 适配 {agent} ==")
    print("已生成文件：")
    for f in created:
        print(f"  - {f}")
    print()
    print(notes)
    return 0
