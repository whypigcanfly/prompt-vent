"""Claude Code CLI 适配（PRD 11.3.1）。

适配方式：
- Slash 命令文件：默认写入用户级 ``~/.claude/commands/``（``--target-dir`` 时写入
  ``<target>/.claude/commands/``，仅生成文件、不改动全局配置，便于打包/二次分发）
- 前置拦截钩子：UserPromptSubmit 钩子，每次用户输入时自动运行 ``ci-pj hook``
  （装饰性、非阻塞）

安装（不带 --target-dir）时自动把钩子合并进 ``~/.claude/settings.json``
（带时间戳备份、幂等去重），无需用户手动编辑配置——对齐 WorkBuddy 适配器的
自动注册体验（issue #1：一键自动安装并自动配置 Claude Code hook）。

``ci-pj hook`` 以 JSON 输出（issue #2）：``systemMessage``=评判行（终端 hook 行可见）+
``hookSpecificOutput.additionalContext`` 注入模型上下文，与 WorkBuddy 同构。
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

# Claude Code 用户级全局配置（钩子注册位置）
GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_EVENT = "UserPromptSubmit"
HOOK_TIMEOUT = 30

# 全局钩子驱动脚本：仅负责定位 ci-pj 并把 hook 事件（stdin 透传）交给 `ci-pj hook`。
# `ci-pj hook` 自身负责解析 Claude Code 传入的 JSON 事件并提取 prompt。
#
# 为什么不用单纯的 `command -v ci-pj`：
#   钩子执行环境（GUI 启动、非交互 shell）的 PATH 不一定包含 ~/.local/bin 或
#   pipx 的 bin 目录，直接 command -v 可能找不到 ci-pj 而静默跳过。
#   这里按优先级显式探测已知安装位置。
HOOK_DRIVER_SH = """#!/usr/bin/env bash
# 词趣判官 · Claude Code 全局钩子驱动（由 UserPromptSubmit 钩子调用）
# 职责：定位 ci-pj 命令，把 hook 事件（JSON，通过 stdin 传入）交给 `ci-pj hook` 处理。
# 退出码 0 = 放行（评判通过 JSON systemMessage 上屏，不拦截用户原始 Prompt）。
set -u
CI_PJ=""
# 优先级：① 本机托管 Python 的 venv 安装（WorkBuddy 托管 venv，pip install 规范位置）
#         ② 用户自带 wrapper（~/.local/bin/ci-pj，含 pipx --user 安装）
#         ③ pipx 规范安装位置
#         ④ 回退到 PATH 中任何 ci-pj
for c in \\
  "$HOME/.workbuddy/binaries/python/envs/default/bin/ci-pj" \\
  "$HOME/.local/bin/ci-pj" \\
  "$HOME/.local/pipx/venvs/ci-prompt-judge/bin/ci-pj" \\
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
        # 默认安装到用户级全局命令目录（所有项目可用）
        return Path.home() / ".claude" / "commands"

    def hook_driver_path(self, target: str | None = None) -> Path:
        if target:
            return Path(target) / ".claude" / "ci-pj" / "hook_driver.sh"
        return Path.home() / ".claude" / "ci-pj" / "hook_driver.sh"

    # ---------- 全局钩子注册（幂等，带备份）----------
    @staticmethod
    def _hook_entry(driver_path: Path) -> dict:
        return {
            "type": "command",
            "command": str(driver_path),
            "timeout": HOOK_TIMEOUT,
        }

    @staticmethod
    def _is_own_hook(command: str, driver_cmd: str) -> bool:
        """判定某钩子 command 是否属于本插件。

        覆盖两种形态：
        - 驱动脚本路径（现行版本注册的 ``~/.claude/ci-pj/hook_driver.sh``）
        - 直接调用 ci-pj 的旧式条目（如 ``~/.local/bin/ci-pj hook``，
          早期手工配置残留；文件被清理后会报 No such file or directory）
        """
        cmd = (command or "").strip()
        return cmd == driver_cmd or cmd.endswith("ci-pj hook")

    @classmethod
    def register_global_hook(cls, driver_path: Path) -> str:
        """把 UserPromptSubmit 钩子合并进 ~/.claude/settings.json（幂等）。返回说明文本。"""
        GLOBAL_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        cmd = str(driver_path)
        # 备份
        bak_path = None
        if GLOBAL_SETTINGS.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            bak_path = GLOBAL_SETTINGS.with_name(f"settings.json.ci-pj-bak-{ts}")
            shutil.copy2(GLOBAL_SETTINGS, bak_path)

        data: dict = {}
        if GLOBAL_SETTINGS.exists():
            try:
                data = json.loads(GLOBAL_SETTINGS.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        hooks = data.setdefault("hooks", {})
        groups = hooks.setdefault(HOOK_EVENT, [])

        # 去重：按 hook 级过滤本插件条目（含旧式直接调用残留），保留同组其他钩子。
        # 不能按组删除：旧条目可能与其他工具的钩子混在同一组，整组删除会误伤（issue #9）
        filtered = []
        for grp in groups:
            hs = (grp.get("hooks") or []) if isinstance(grp, dict) else []
            kept = [h for h in hs if not cls._is_own_hook(h.get("command", ""), cmd)]
            if kept:
                grp = dict(grp)
                grp["hooks"] = kept
                filtered.append(grp)
        filtered.append({"hooks": [cls._hook_entry(driver_path)]})
        hooks[HOOK_EVENT] = filtered
        data["hooks"] = hooks

        GLOBAL_SETTINGS.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        note = (
            f"已注册全局钩子：~/.claude/settings.json 的 hooks.{HOOK_EVENT}\n"
            f"  驱动：{cmd}\n"
        )
        if bak_path:
            note += f"  已备份原配置到：{bak_path}\n"
        note += "  重启 Claude Code 后生效；每次提交消息将自动运行 ci-pj hook 做前置点评。\n"
        note += "  卸载：ci-pj uninstall claude_code"
        return note

    @classmethod
    def unregister_global_hook(cls, driver_path: Path) -> str:
        """从 ~/.claude/settings.json 移除本插件的钩子（幂等）。返回说明文本。"""
        cmd = str(driver_path)
        if not GLOBAL_SETTINGS.exists():
            return "未找到 ~/.claude/settings.json，无需卸载钩子。"
        try:
            data = json.loads(GLOBAL_SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return ("~/.claude/settings.json 解析失败，请手动检查并移除 "
                    f"hooks.{HOOK_EVENT} 中指向本插件的钩子。")
        hooks = data.get("hooks", {})
        groups = hooks.get(HOOK_EVENT, [])
        kept = []
        removed = 0
        for grp in groups:
            hs = (grp.get("hooks") or []) if isinstance(grp, dict) else []
            # hook 级过滤：只移除本插件条目（驱动脚本 / 旧式直接调用残留），
            # 保留同组其他工具的钩子（issue #9）
            kept_hooks = [h for h in hs
                          if not cls._is_own_hook(h.get("command", ""), cmd)]
            removed += len(hs) - len(kept_hooks)
            if kept_hooks:
                grp = dict(grp)
                grp["hooks"] = kept_hooks
                kept.append(grp)
        if removed == 0:
            return "~/.claude/settings.json 中未找到本插件钩子，无需卸载。"
        if kept:
            hooks[HOOK_EVENT] = kept
        else:
            hooks.pop(HOOK_EVENT, None)
        if hooks:
            data["hooks"] = hooks
        else:
            data.pop("hooks", None)
        GLOBAL_SETTINGS.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return f"已移除 {removed} 个本插件钩子；重启 Claude Code 后生效。"

    # ---------- 卸载：精确删除本插件文件，不碰用户其他命令 ----------
    def uninstall_files(self) -> List[str]:
        removed: List[str] = []
        d = self.install_dir(None)  # ~/.claude/commands
        for name in COMMANDS:
            f = d / f"{name}.md"
            if f.exists():
                f.unlink()
                removed.append(str(f))
        # 老版本生成的钩子片段文件（现已自动注册，不再生成）
        legacy = d.parent / "settings.ci-pj.hook.json"
        if legacy.exists():
            legacy.unlink()
            removed.append(str(legacy))
        driver = self.hook_driver_path()
        if driver.exists():
            driver.unlink()
            removed.append(str(driver))
            try:
                driver.parent.rmdir()  # 仅当目录已空才删
            except OSError:
                pass
        return removed

    def generate(self, target: str | None = None) -> Tuple[List[str], str]:
        d = self.install_dir(target)
        d.mkdir(parents=True, exist_ok=True)
        created: List[str] = []

        # 1) Slash 命令文件
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

        # 2) 全局钩子驱动脚本
        driver_path = self.hook_driver_path(target)
        driver_path.parent.mkdir(parents=True, exist_ok=True)
        driver_path.write_text(HOOK_DRIVER_SH, encoding="utf-8")
        try:
            driver_path.chmod(0o755)
        except Exception:
            pass
        created.append(str(driver_path))

        notes = (
            "Claude Code 安装说明：\n"
            "1) 确保 ci-pj 已安装且可被找到：`pip install ci-prompt-judge` 或 `pip install -e .`\n"
            "   （钩子驱动按 托管venv → ~/.local/bin → pipx → PATH 顺序自动定位）\n"
            f"2) 命令文件已写入 {d}（pj-mode / pj-status / pj-update / pj-judge）\n"
        )
        if target:
            # 指定了目标目录：仅生成文件，不改动本机全局配置（便于打包/二次分发）
            notes += (
                "3) 你指定了 --target-dir，未改动本机全局配置。\n"
                "   若要启用全局自动前置点评，请手动把以下钩子合并进 "
                f"~/.claude/settings.json 的 hooks.{HOOK_EVENT}：\n"
                f'   {{ "type": "command", "command": "{driver_path}", "timeout": {HOOK_TIMEOUT} }}\n'
                "   或直接运行（不带 --target-dir）：ci-pj install claude_code\n"
                "   （UserPromptSubmit 钩子读取 stdin JSON 的 prompt 字段，运行 `ci-pj hook` 自动评判）\n"
            )
            return created, notes

        # 3) 默认：自动注册全局钩子
        hook_note = self.register_global_hook(driver_path)
        notes += (
            "3) 已自动注册全局 UserPromptSubmit 钩子（~/.claude/settings.json），"
            "每次提交消息自动前置点评。\n"
            "4) 评判行通过 hook JSON systemMessage 上屏（终端 hook 行可见），"
            "并经 additionalContext 注入模型上下文（issue #2）。\n"
            "5) 使用：/pj-mode 渣女 切换人设；普通对话会自动前缀趣味评判后放行。\n"
            "注意：钩子仅做装饰性输出，不影响原 Prompt 执行；如不想自动评判，"
            "运行 ci-pj uninstall claude_code 移除钩子（仍可手动 /pj-judge）。\n"
            "---- 钩子注册 ----\n" + hook_note
        )
        return created, notes
