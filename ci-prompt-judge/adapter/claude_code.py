"""Claude Code CLI 适配（PRD 11.3.1）。

适配方式：
- Slash 命令文件：.claude/commands/ 下生成 pj-mode / pj-status / pj-update / pj-judge
- 前置拦截钩子：UserPromptSubmit 钩子，每次用户输入时自动运行 ci-pj hook（装饰性、非阻塞）
  自动幂等合并进项目级 .claude/settings.json（写前自动备份），无需手动合并片段。
  `ci-pj hook` 以 JSON 输出（systemMessage=评判行上屏 + hookSpecificOutput.additionalContext
  注入模型上下文），与 WorkBuddy 同构。
"""
from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path
from typing import List, Tuple

from adapter.base import AgentAdapter

COMMANDS = {
    "pj-mode": "切换/关闭词趣判官人设",
    "pj-status": "查询词趣判官状态",
    "pj-update": "联网增量更新话术（需 WebSearch）",
    "pj-judge": "手动对一段 Prompt 做趣味评判",
}

HOOK_EVENT = "UserPromptSubmit"
HOOK_TIMEOUT = 30

# 项目级钩子驱动脚本：仅负责定位 ci-pj 并把 hook 事件（stdin 透传）交给 `ci-pj hook`。
# 为什么不用单纯的 `ci-pj hook`：Claude Code 执行钩子时的 PATH 不一定包含用户的
# venv bin 或 ~/.local/bin，直接找 ci-pj 可能失败而静默跳过。按优先级显式探测已知安装位置。
HOOK_DRIVER_SH = """#!/usr/bin/env bash
# 词趣判官 · Claude Code 项目级钩子驱动（由 UserPromptSubmit 钩子调用）
# 职责：定位 ci-pj 命令，把 hook 事件（JSON，通过 stdin 传入）交给 `ci-pj hook` 处理。
# 退出码 0 = 放行（评判通过 JSON systemMessage 上屏，不拦截用户原始 Prompt）。
set -u
CI_PJ=""
# 优先级：① 本机托管 Python 的 venv 安装（pip install 的规范位置，含最新代码）
#         ② 用户自带的 wrapper（~/.local/bin/ci-pj）
#         ③ 回退到 PATH 中任何 ci-pj
for c in \\
  "$HOME/.workbuddy/binaries/python/envs/default/bin/ci-pj" \\
  "$HOME/.local/bin/ci-pj" \\
  "$(command -v ci-pj 2>/dev/null || true)"; do
  if [ -n "$c" ] && [ -x "$c" ]; then
    CI_PJ="$c"
    break
  fi
done
if [ -z "$CI_PJ" ]; then
  # ci-pj 未安装：静默放行，不影响正常使用
  exit 0
fi
exec "$CI_PJ" hook
"""


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

    def hooks_dir(self, target: str | None) -> Path:
        if target:
            return Path(target) / ".claude" / "hooks"
        return Path.cwd() / ".claude" / "hooks"

    def settings_path(self, target: str | None) -> Path:
        if target:
            return Path(target) / ".claude" / "settings.json"
        return Path.cwd() / ".claude" / "settings.json"

    # ---------- 项目级钩子注册（幂等，带备份）----------
    @staticmethod
    def _hook_entry(driver_path: Path) -> dict:
        return {
            "type": "command",
            "command": str(driver_path),
            "timeout": HOOK_TIMEOUT,
        }

    def register_project_hook(self, driver_path: Path, target: str | None = None) -> str:
        """把 UserPromptSubmit 钩子合并进项目级 .claude/settings.json（幂等）。返回说明文本。"""
        settings = self.settings_path(target)
        settings.parent.mkdir(parents=True, exist_ok=True)
        cmd = str(driver_path)
        # 备份
        bak_path = None
        if settings.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            bak_path = settings.with_name(f"settings.json.ci-pj-bak-{ts}")
            shutil.copy2(settings, bak_path)

        data: dict = {}
        if settings.exists():
            try:
                data = json.loads(settings.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        hooks = data.setdefault("hooks", {})
        groups = hooks.setdefault(HOOK_EVENT, [])

        # 去重：移除任何已包含本驱动命令的钩子组，避免重复注册
        filtered = []
        for grp in groups:
            hs = grp.get("hooks") or [] if isinstance(grp, dict) else []
            if any(h.get("command") == cmd for h in hs):
                continue
            filtered.append(grp)
        filtered.append({"hooks": [self._hook_entry(driver_path)]})
        hooks[HOOK_EVENT] = filtered
        data["hooks"] = hooks

        settings.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        note = (
            f"已注册项目级钩子：{settings} 的 hooks.{HOOK_EVENT}\n"
            f"  驱动：{cmd}\n"
        )
        if bak_path:
            note += f"  已备份原配置到：{bak_path}\n"
        note += "  重启 Claude Code 会话后生效；每次提交消息将自动运行 ci-pj hook 做前置点评。\n"
        return note

    def unregister_project_hook(self, target: str | None = None) -> str:
        """从项目级 settings.json 移除本插件的钩子（幂等）。返回说明文本。"""
        settings = self.settings_path(target)
        if not settings.exists():
            return "未找到项目级 .claude/settings.json，无需卸载钩子。"
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except Exception:
            return "项目级配置解析失败，请手动检查 .claude/settings.json。"
        hooks = data.get("hooks", {})
        groups = hooks.get(HOOK_EVENT, [])
        kept = []
        removed = 0
        for grp in groups:
            hs = grp.get("hooks") or [] if isinstance(grp, dict) else []
            if any(
                isinstance(h, dict) and str(h.get("command", "")).endswith("ci-pj-hook.sh")
                for h in hs
            ):
                removed += 1
                continue
            kept.append(grp)
        if removed == 0:
            return "项目级配置中未找到本插件的钩子，无需卸载。"
        hooks[HOOK_EVENT] = kept
        if not hooks.get(HOOK_EVENT):
            hooks.pop(HOOK_EVENT, None)
        if hooks:
            data["hooks"] = hooks
        else:
            data.pop("hooks", None)
        settings.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return f"已移除 {removed} 个本插件钩子（{settings}）；重启 Claude Code 会话后生效。"

    def uninstall(self, target: str | None = None) -> str:
        """定制卸载：只清理本插件产物，不动用户其他命令文件。供 installer 调用。"""
        notes: List[str] = []
        hook_note = self.unregister_project_hook(target)
        notes.append(hook_note)

        # 命令文件：只删本插件生成的 pj-*.md，不删整个目录
        commands_dir = self.install_dir(target)
        removed: List[str] = []
        if commands_dir.exists():
            for f in sorted(commands_dir.glob("pj-*.md")):
                f.unlink()
                removed.append(str(f))
        # 钩子驱动脚本
        driver = self.hooks_dir(target) / "ci-pj-hook.sh"
        if driver.exists():
            driver.unlink()
            removed.append(str(driver))
        # 空目录顺手清理（仅在本插件目录为空时）
        for d in (commands_dir, driver.parent):
            try:
                d.rmdir()
            except OSError:
                pass
        if removed:
            notes.append("已删除：\n" + "\n".join(f"  - {f}" for f in removed))
        return "\n".join(notes)

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

        # 钩子驱动脚本（探测 ci-pj 路径，避免钩子执行环境 PATH 缺失）
        hooks_d = self.hooks_dir(target)
        hooks_d.mkdir(parents=True, exist_ok=True)
        driver_path = hooks_d / "ci-pj-hook.sh"
        driver_path.write_text(HOOK_DRIVER_SH, encoding="utf-8")
        try:
            driver_path.chmod(0o755)
        except Exception:
            pass
        created.append(str(driver_path))

        notes = (
            "Claude Code 安装说明：\n"
            "1) 确保 ci-pj 已安装：`pip install -e .` 或 `pip install ci-prompt-judge`\n"
            "   （钩子驱动会按 venv → ~/.local/bin → PATH 顺序自动定位，无需手动配置 PATH）\n"
            "2) 已将命令文件写入 .claude/commands/（pj-mode / pj-status / pj-update / pj-judge）\n"
            "3) 钩子驱动已写入 .claude/hooks/ci-pj-hook.sh\n"
        )
        if target:
            # 指定了目标目录：仅生成文件，不改动项目级配置（便于打包/二次分发）
            notes += (
                "4) 你指定了 --target-dir，未改动项目级配置。\n"
                "   若要启用自动前置点评，请手动把以下钩子合并进 .claude/settings.json 的 "
                f"hooks.{HOOK_EVENT}：\n"
                f'   {{ "type": "command", "command": "{driver_path}", "timeout": {HOOK_TIMEOUT} }}\n'
                "   或直接运行（不带 --target-dir）：ci-pj install claude_code\n"
                "   卸载：ci-pj uninstall claude_code（只清理本插件产物，不动其他命令）"
            )
            return created, notes

        # 4) 默认：自动注册项目级钩子（幂等、带备份）
        hook_note = self.register_project_hook(driver_path, target)
        notes += (
            "4) 已自动注册项目级 UserPromptSubmit 钩子（.claude/settings.json，写前自动备份），\n"
            "   每次提交消息自动前置点评；评判行通过 hook JSON systemMessage 上屏，早于模型回复。\n"
            "5) 使用：/pj-mode 渣女 切换人设；普通对话会自动前缀趣味评判后放行。\n"
            "注意：钩子仅做装饰性输出，不影响原 Prompt 执行；如不想自动评判，"
            "运行 ci-pj uninstall claude_code 即可（仍可手动 /pj-judge）。"
        )
        notes += "\n---- 钩子注册 ----\n" + hook_note
        return created, notes
