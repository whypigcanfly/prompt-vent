"""Claude Code CLI 适配（PRD 11.3.1）。

适配方式：
- Slash 命令文件：.claude/commands/ 下生成 pj-mode / pj-status / pj-update / pj-judge
- 前置拦截钩子：UserPromptSubmit 钩子，每次用户输入时自动运行 ci-pj hook（装饰性、非阻塞）
命令文件通过 `!` 调用本地 ci-pj 可执行（需先 pip install 或确保 ci-pj 在 PATH）。
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


class ClaudeCodeAdapter(AgentAdapter):
    name = "claude_code"
    supports_command_file = True

    def command_filename(self) -> str:
        return "pj.md"

    def command_content(self) -> str:
        return ""

    def install_dir(self, target: str | None) -> Path:
        if target:
            return Path(target) / ".claude" / "commands"
        return Path.cwd() / ".claude" / "commands"

    def generate(self, target: str | None = None) -> Tuple[List[str], str]:
        d = self.install_dir(target)
        d.mkdir(parents=True, exist_ok=True)
        created: List[str] = []
        for name, desc in COMMANDS.items():
            cf = d / f"{name}.md"
            content = (
                f"---\n"
                f"description: 词趣判官 - {desc}\n"
                f"---\n"
                f"!ci-pj run \"$ARGUMENTS\"\n"
            )
            cf.write_text(content, encoding="utf-8")
            created.append(str(cf))

        # 钩子配置片段（合并进 .claude/settings.json 的 hooks.UserPromptSubmit）
        hook_snippet = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "ci-pj hook",
                            }
                        ]
                    }
                ]
            }
        }
        snippet_path = d.parent / "settings.ci-pj.hook.json"
        self.write_json(snippet_path, hook_snippet)
        created.append(str(snippet_path))

        notes = (
            "Claude Code 安装说明：\n"
            "1) 确保 ci-pj 已安装且在 PATH：`pip install -e .` 或 `pip install ci-prompt-judge`\n"
            "2) 已将命令文件写入 .claude/commands/（pj-mode / pj-status / pj-update / pj-judge）\n"
            "3) 钩子片段已生成 .claude/settings.ci-pj.hook.json，请将其 hooks 节点合并进现有 .claude/settings.json\n"
            "   （UserPromptSubmit 钩子读取 stdin JSON 的 prompt 字段，运行 `ci-pj hook` 自动评判）\n"
            "4) 使用：/pj-mode 渣女 切换人设；普通对话会自动前缀趣味评判后放行。\n"
            "注意：钩子仅做装饰性输出，不影响原 Prompt 执行；如不想自动评判，删除该钩子即可（仍可手动 /pj-judge）。"
        )
        return created, notes
