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


def uninstall(agent: str) -> int:
    try:
        adapter = _resolve(agent)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    # 适配器提供定制卸载（如 claude_code：只清理本插件产物，不动用户其他命令文件）
    if hasattr(adapter, "uninstall"):
        print(f"== 卸载 词趣判官 适配 {agent} ==")
        try:
            note = adapter.uninstall()
        except Exception as e:  # noqa: BLE001
            print(f"卸载失败：{e}", file=sys.stderr)
            return 1
        print(note)
        print("提示：核心包（ci-pj 命令）仍可用；如需彻底移除请 pip uninstall ci-prompt-judge。")
        return 0
    # 先反注册全局钩子（若支持）
    unreg_note = ""
    if hasattr(adapter, "unregister_global_hook"):
        d = adapter.install_dir(None)
        driver = d / "hook_driver.sh"
        try:
            unreg_note = adapter.unregister_global_hook(driver)
        except Exception as e:  # noqa: BLE001
            unreg_note = f"反注册钩子时出错：{e}"
    # 再删除生成的技能/文件目录
    removed = []
    try:
        d = adapter.install_dir(None)
        if d.exists():
            import shutil

            shutil.rmtree(d)
            removed.append(str(d))
    except Exception as e:  # noqa: BLE001
        print(f"删除目录失败：{e}", file=sys.stderr)
    print(f"== 卸载 词趣判官 适配 {agent} ==")
    if unreg_note:
        print(unreg_note)
    if removed:
        print("已删除：")
        for f in removed:
            print(f"  - {f}")
    print("提示：核心包（ci-pj 命令）仍可用；如需彻底移除请 pip uninstall ci-prompt-judge。")
    return 0
