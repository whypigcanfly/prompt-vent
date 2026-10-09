"""Hermes 通用 Agent 适配（PRD 11.3.2）。

Hermes 多轮连续对话、自动化任务场景。适配方式同通用命令 + 钩子，
并说明多轮上下文连续评判、状态实时切换不串模的注意点。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from adapter.base import AgentAdapter

COMMANDS = {
    "pj-mode": "切换/关闭词趣判官人设",
    "pj-status": "查询词趣判官状态",
    "pj-update": "联网增量更新话术（需 WebSearch）",
    "pj-judge": "手动对一段 Prompt 做趣味评判",
}


class HermesAdapter(AgentAdapter):
    name = "hermes"
    supports_command_file = True

    def command_filename(self) -> str:
        return "pj.md"

    def command_content(self) -> str:
        return ""

    def install_dir(self, target: str | None) -> Path:
        if target:
            return Path(target) / ".hermes" / "commands"
        return Path.cwd() / ".hermes" / "commands"

    def generate(self, target: str | None = None) -> Tuple[List[str], str]:
        d = self.install_dir(target)
        d.mkdir(parents=True, exist_ok=True)
        created: List[str] = []
        for name, desc in COMMANDS.items():
            cf = d / f"{name}.md"
            cf.write_text(
                f"---\n"
                f"description: 词趣判官 - {desc}\n"
                f"---\n"
                f"!ci-pj run \"$ARGUMENTS\"\n",
                encoding="utf-8",
            )
            created.append(str(cf))

        notes = (
            "Hermes 安装说明：\n"
            "1) 安装 ci-pj：`pip install -e .`\n"
            "2) 命令文件已写入 .hermes/commands/\n"
            "3) 前置拦截：在 Hermes 的输入预处理环节挂载 `ci-pj hook`（读取 prompt），每次用户输入后先评判再继续\n"
            "4) 多轮场景：状态存于 ~/.ci-pj/state.json，跨轮切换人设不串模；连续高频输入每次独立打分\n"
            "5) 使用：/pj-mode 激励师 切换人设；普通对话自动前缀评判后放行。"
        )
        return created, notes
