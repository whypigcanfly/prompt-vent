"""Codex 适配（PRD 11.1 预设 Agent 之一，best-effort）。

Codex 同样支持自定义命令与钩子（具体随版本演进）。本适配器生成命令文件与钩子片段，
并以注释说明 Codex 专属配置位置，避免误写覆盖。
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


class CodexAdapter(AgentAdapter):
    name = "codex"
    supports_command_file = True

    def command_filename(self) -> str:
        return "pj.md"

    def command_content(self) -> str:
        return ""

    def install_dir(self, target: str | None) -> Path:
        if target:
            return Path(target) / ".codex" / "commands"
        return Path.cwd() / ".codex" / "commands"

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
            "Codex 安装说明（best-effort，请按所用 Codex 版本核对）：\n"
            "1) 安装 ci-pj：`pip install -e .`\n"
            "2) 命令文件已写入 .codex/commands/（若你的 Codex 版本命令目录不同，请移动到对应位置）\n"
            "3) 前置拦截：在 Codex 配置中注册 PreTool/UserPrompt 钩子，命令为 `ci-pj hook`（读取 stdin prompt）\n"
            "4) 使用：/pj-mode 渣女 切换人设；普通对话经钩子自动前缀评判后放行。\n"
            "提示：若 Codex 版本不支持命令文件，可改为在 AGENTS.md / 系统提示中声明："
            "「用户以 /pj- 开头的输入交给 ci-pj 处理；其余输入先运行 ci-pj hook 再做回答」。"
        )
        return created, notes
