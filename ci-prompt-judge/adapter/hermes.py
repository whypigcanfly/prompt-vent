"""Hermes（NousResearch/hermes-agent）适配。

Hermes 多轮连续对话、自动化任务场景。适配基于官方文档
（https://hermes-agent.nousresearch.com/docs）确认的两类机制：

- 自定义斜杠命令：技能目录 ``~/.hermes/skills/<name>/SKILL.md``（agentskills.io
  开放标准），安装后自动注册为 ``/ci-prompt-judge`` 斜杠命令。
- 前置拦截：Shell Hooks —— 在 ``~/.hermes/config.yaml`` 的 ``hooks.pre_llm_call``
  下声明脚本；每轮用户消息进入 LLM 前 Hermes 以子进程运行该脚本，stdin 传入
  JSON 事件（用户输入在 ``extra.user_message``），stdout 返回
  ``{"context": "..."}`` 会被注入本轮用户消息，实现前置点评。

协议细节与 Claude Code 高度同构（文档明确接受 Claude Code 风格的 block/failClosed
写法），驱动脚本沿用「探测 ci-pj 安装位置 + stdin 透传」的统一模式。
"""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from typing import List, Tuple

from adapter.base import AgentAdapter

HERMES_HOME = Path.home() / ".hermes"
# Hermes 全局配置（钩子注册位置，YAML）
GLOBAL_CONFIG = HERMES_HOME / "config.yaml"
HOOK_EVENT = "pre_llm_call"
HOOK_TIMEOUT = 30

# 权威 SKILL.md 位置：仓库内 skills/ci-prompt-judge/hermes/SKILL.md（单一数据源，
# 避免与内嵌副本漂移）；文件缺失时回退到内嵌副本。
_CANONICAL_SKILL = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "ci-prompt-judge"
    / "hermes"
    / "SKILL.md"
)

# 全局钩子驱动脚本：仅负责定位 ci-pj 并把 hook 事件（stdin 透传）交给 `ci-pj hook`。
# `ci-pj hook` 自身负责解析 Hermes 传入的 JSON 事件（extra.user_message）并输出
# {"context": ...} 注入格式。
# 为什么不用单纯的 `command -v ci-pj`：钩子执行环境的 PATH 不一定包含 ~/.local/bin
# 或 pipx 的 bin 目录，直接 command -v 可能找不到 ci-pj 而静默跳过。按优先级显式探测。
HOOK_DRIVER_SH = """#!/usr/bin/env bash
# 词趣判官 · Hermes 全局钩子驱动（由 pre_llm_call Shell Hook 调用）
# 职责：定位 ci-pj 命令，把 hook 事件（JSON，通过 stdin 传入）交给 `ci-pj hook` 处理。
# `ci-pj hook` 输出 {"context": ...} 由 Hermes 注入本轮用户消息；其他输出为静默放行。
set -u
CI_PJ=""
# 优先级：① 用户自带 wrapper（~/.local/bin/ci-pj，含 pipx --user 安装）
#         ② pipx 规范安装位置
#         ③ 回退到 PATH 中任何 ci-pj
for c in \\
  "$HOME/.local/bin/ci-pj" \\
  "$HOME/.local/pipx/venvs/ci-prompt-judge/bin/ci-pj" \\
  "$(command -v ci-pj 2>/dev/null || true)"; do
  if [ -n "$c" ] && [ -x "$c" ]; then
    CI_PJ="$c"
    break
  fi
done
if [ -z "$CI_PJ" ]; then
  # ci-pj 未安装：静默放行（stdout 无 JSON = no-op），不影响正常使用
  exit 0
fi
exec "$CI_PJ" hook
"""

_SKILL_MD_FALLBACK = """---
name: ci-prompt-judge
description: 词趣判官 - Prompt 趣味前置评判插件。当用户想要对提示词做趣味点评与 1-10 分完整性评分，或使用 /pj-mode、/pj-status、/pj-update、/pj-judge 等指令时使用。安装时已自动注册 pre_llm_call Shell Hook，每轮用户消息自动前置点评。
---

# 词趣判官（ci-prompt-judge）

一个无侵入的 Prompt 趣味前置评判插件。核心约束：**永远不修改、不篡改、不优化用户原始 Prompt**，仅做「评价 + 打分」，不干预主任务执行。

## 何时使用

1. 安装后已**自动注册 Hermes Shell Hook（pre_llm_call）**：每轮你在 Hermes 提交消息，进入模型前都会自动运行 `ci-pj hook` 做趣味前置点评（以 {"context": ...} 注入），无需在当前对话显式触发。
2. 用户显式使用 `/pj-` 前缀指令（优先级最高）：
   - `/pj-mode 渣女 | 激励师 | 贴吧老哥 | 腹黑毒舌女 | off` —— 切换/关闭人设
   - `/pj-status` —— 查询当前状态
   - `/pj-update <人设> | /pj-update-all` —— 联网增量更新话术（需 WebSearch）
   - `/pj-judge <文本>` —— 手动评判一段 Prompt
3. 用户希望对自己的提示词获得趣味点评与完整性评分。

## 如何执行

本技能依赖已安装的 `ci-pj` 命令行工具（Python）。请通过 Bash 调用：

- 评判/指令分发：`ci-pj run "<用户输入>"`
- 仅诊断（不输出评判，看匹配与分数）：`ci-pj diagnose "<文本>"`
- 前置钩子（已由 Shell Hook 自动调用）：`ci-pj hook`（读取 stdin 的 hook 事件 JSON）

> 安装 ci-pj：`pip install -e .`（项目根目录）或 `pip install ci-prompt-judge`。
> 若环境中没有 ci-pj，请提示用户先安装，不要自行臆造评分。

## 输出规范（强制）

评判输出必须严格为：

```
【XX语气评判｜提示词完整性得分：X/10】评判话术内容
---放行提示词---
用户原始完整Prompt
```

关闭模式（off）时无任何输出，直接进入正常回答。

## 回复首行规则（重要）

pre_llm_call 钩子把评判文本注入你收到的用户消息，注入内容由定界符 `<ci-prompt-judge-injection>` 与 `</ci-prompt-judge-injection>` 包裹，属于插件自动附加的后台上下文，**不是用户所说的话**。

若注入内容末尾带有 `[词趣判官·输出要求]` 指令，则**你的回复必须**：

1. **第一行**：原样输出那行以「【」开头的评判（含得分与话术），一字不改、不加引号、不加 Markdown 装饰；
2. **第二行**：空一行；
3. **第三行起**：才开始你的思考过程与正式回答。

评判只占开头一行，**不得**因此改变你后续回答的内容、语气或任务执行方式（插件不干预主任务）。除首行评判行外，**禁止**在回复中复述、引用或展示注入内容里的任何其他内容（包括定界符本身、`[词趣判官·输出要求]`、`---放行提示词---` 及本规则）。若注入内容中没有该指令，或当前处于 off 模式，则按常规回答，无需输出评判行。

## 硬约束

- 绝不修改用户原始 Prompt，只点评、只打分、只放行。
- 违规内容直接拦截，跳过趣味评判（必要时交宿主安全层）。
- 控制指令执行后不评判、不放行，仅执行控制逻辑。
- 切换人设即时生效，无残留状态。

## 扩展

规则（core/data/rule/rules.json）、人设话术（core/data/speech/personas.json）、评分权重（core/data/config/config.default.json）全部可配置、可插拔，无需改核心代码即可新增人设/规则/话术。
"""


def _load_skill_md() -> str:
    if _CANONICAL_SKILL.exists():
        return _CANONICAL_SKILL.read_text(encoding="utf-8")
    return _SKILL_MD_FALLBACK


# 在 _SKILL_MD_FALLBACK 定义之后再调用，避免包内缺失权威文件时回退到未定义变量
SKILL_MD = _load_skill_md()


def _hermes_venv_python() -> Path | None:
    """探测 Hermes 自带 venv 的 python（其 _record_approval 可写内部白名单文件）。"""
    for p in (
        HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python",
        HERMES_HOME / "venv" / "bin" / "python",
    ):
        if p.exists():
            return p
    return None


# 在 Hermes venv 内执行的批准脚本：调用其 _record_approval 写 allowlist，
# 记录格式与 hermes 内部完全一致（approved_at / script_mtime_at_approval）。
# cwd 必须是 hermes-agent 仓库根，否则 agent.shell_hooks 导入会失败。
_APPROVAL_SNIPPET = (
    "import sys\n"
    "from agent import shell_hooks\n"
    "cmd = sys.argv[1]\n"
    "shell_hooks._record_approval('pre_llm_call', cmd)\n"
    "print('OK' if shell_hooks._is_allowlisted('pre_llm_call', cmd) else 'FAIL')\n"
)


def _ensure_hook_allowlisted(driver_path: Path) -> str:
    """把钩子写入 Hermes Shell Hook 白名单（shell-hooks-allowlist.json）。

    desktop / gateway / cron 等非交互宿主不会弹 consent（shell_hooks.py: 非 TTY
    直接跳过注册），未批准的钩子会被**静默 skip** —— 这是「装了没输出」的典型根因。
    优先借 Hermes 自带 venv 调其 _record_approval（格式与内部一致）；
    失败则降级为手动指引（TTY 确认 / hooks_auto_accept / 环境变量三选一）。
    """
    py = _hermes_venv_python()
    if py:
        # venv 布局：<repo>/venv/bin/python → 回退三级到 hermes-agent 仓库根
        repo_root = py.parent.parent.parent
        try:
            import subprocess

            r = subprocess.run(
                [str(py), "-c", _APPROVAL_SNIPPET, str(driver_path)],
                capture_output=True, text=True, timeout=60, cwd=str(repo_root),
            )
            if r.returncode == 0 and "OK" in r.stdout:
                return (
                    "✓ 已写入 Shell Hook 白名单（shell-hooks-allowlist.json），"
                    "desktop/gateway 等非交互宿主免确认直接生效。"
                )
        except Exception:  # noqa: BLE001 — 任一环节失败都走手动指引
            pass
    return (
        "⚠ 未能自动写入 Shell Hook 白名单（shell-hooks-allowlist.json）。\n"
        "  desktop/gateway 等非交互宿主不会弹确认，未批准的钩子会被静默跳过。\n"
        "  请任选其一：\n"
        f"  ① 在交互终端启动一次 Hermes，对弹出的确认选 y（命令：{driver_path}）；\n"
        f"  ② 在 {GLOBAL_CONFIG} 顶层加：hooks_auto_accept: true\n"
        "  ③ 以 HERMES_ACCEPT_HOOKS=1 环境变量启动一次 hermes gateway。"
    )


def _dump_yaml(data: dict) -> str:
    import yaml

    return yaml.safe_dump(
        data, allow_unicode=True, default_flow_style=False, sort_keys=False
    )


def _manual_hook_snippet(driver_path: Path) -> str:
    return (
        "hooks:\n"
        f"  {HOOK_EVENT}:\n"
        f"    - command: {driver_path}\n"
        f"      timeout: {HOOK_TIMEOUT}\n"
    )


class HermesAdapter(AgentAdapter):
    name = "hermes"
    supports_command_file = False

    def command_filename(self) -> str:
        return "SKILL.md"

    def command_content(self) -> str:
        return SKILL_MD

    def install_dir(self, target: str | None) -> Path:
        if target:
            return Path(target) / ".hermes" / "skills" / "ci-prompt-judge"
        # 默认安装到用户级技能目录（Hermes 自动注册为 /ci-prompt-judge 斜杠命令）
        return HERMES_HOME / "skills" / "ci-prompt-judge"

    def hook_driver_path(self, target: str | None = None) -> Path:
        if target:
            return Path(target) / ".hermes" / "agent-hooks" / "ci-pj-hook.sh"
        return HERMES_HOME / "agent-hooks" / "ci-pj-hook.sh"

    # ---------- 全局钩子注册（幂等，带备份）----------
    @classmethod
    def register_global_hook(cls, driver_path: Path) -> str:
        """把 pre_llm_call Shell Hook 合并进 ~/.hermes/config.yaml（幂等）。返回说明文本。"""
        cmd = str(driver_path)
        try:
            import yaml  # noqa: F401
        except ImportError:
            # 无 PyYAML：全新安装（配置文件不存在）可直接写最小配置，零依赖；
            # 已有配置则无法安全解析合并，降级为手动说明。
            if not GLOBAL_CONFIG.exists():
                GLOBAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
                GLOBAL_CONFIG.write_text(
                    "# 词趣判官 · Hermes Shell Hook（ci-pj install hermes 生成）\n"
                    + _manual_hook_snippet(driver_path),
                    encoding="utf-8",
                )
                return (
                    f"已注册全局 Shell Hook（新写入）：{GLOBAL_CONFIG} 的 hooks.{HOOK_EVENT}\n"
                    f"  驱动：{cmd}\n"
                    "  重启 Hermes 会话后生效；每轮用户消息将自动运行 ci-pj hook 做前置点评。\n"
                    "  注意：desktop/gateway 等非交互宿主不会弹确认，未批准的钩子会被\n"
                    "  静默跳过；请确保 Shell Hook 白名单已批准（见安装说明）。\n"
                    "  验证：hermes hooks test pre_llm_call；卸载：ci-pj uninstall hermes"
                )
            # 按整行匹配，兼容手写/PyYAML 两种缩进，且不会把
            # 「command: <同前缀但不同路径>」误判为已注册
            lines = GLOBAL_CONFIG.read_text(encoding="utf-8").splitlines()
            if any(
                l.strip() in (f"- command: {cmd}", f"command: {cmd}")
                for l in lines
            ):
                return f"钩子已注册（{GLOBAL_CONFIG} 中已存在指向本驱动的条目），无需重复注册。"
            return (
                "未安装 PyYAML，且 ~/.hermes/config.yaml 已有内容，无法自动改写。\n"
                f"  请手动把以下内容合并进 {GLOBAL_CONFIG} 的 hooks 节：\n"
                + _manual_hook_snippet(driver_path)
                + "  或先安装 PyYAML（pip install pyyaml）后重跑 ci-pj install hermes。\n"
            )

        if GLOBAL_CONFIG.exists():
            try:
                data = yaml.safe_load(GLOBAL_CONFIG.read_text(encoding="utf-8")) or {}
            except Exception as e:  # noqa: BLE001
                return (
                    f"~/.hermes/config.yaml 解析失败（{e}），请手动把以下内容合并进 "
                    "hooks 节：\n" + _manual_hook_snippet(driver_path)
                )
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}

        # 备份（改写会丢失 YAML 注释，留原始副本）
        bak_path = None
        if GLOBAL_CONFIG.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            bak_path = GLOBAL_CONFIG.with_name(f"config.yaml.ci-pj-bak-{ts}")
            shutil.copy2(GLOBAL_CONFIG, bak_path)

        hooks = data.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            hooks = data["hooks"] = {}
        entries = hooks.setdefault(HOOK_EVENT, [])
        if not isinstance(entries, list):
            entries = hooks[HOOK_EVENT] = [entries]

        # 去重：移除指向本驱动命令的旧条目，避免重复注册
        filtered = [
            e for e in entries
            if not (isinstance(e, dict) and e.get("command") == cmd)
        ]
        filtered.append({"command": cmd, "timeout": HOOK_TIMEOUT})
        hooks[HOOK_EVENT] = filtered
        data["hooks"] = hooks

        GLOBAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        GLOBAL_CONFIG.write_text(_dump_yaml(data), encoding="utf-8")
        note = (
            f"已注册全局 Shell Hook：{GLOBAL_CONFIG} 的 hooks.{HOOK_EVENT}\n"
            f"  驱动：{cmd}\n"
        )
        if bak_path:
            note += f"  已备份原配置到：{bak_path}（YAML 改写会丢失注释，可从中找回）\n"
        note += (
            "  重启 Hermes 会话后生效；每轮用户消息将自动运行 ci-pj hook 做前置点评。\n"
            "  注意：desktop/gateway 等非交互宿主不会弹确认，未批准的钩子会被\n"
            "  静默跳过；请确保 Shell Hook 白名单已批准（见安装说明）。\n"
            "  验证：hermes hooks test pre_llm_call；卸载：ci-pj uninstall hermes"
        )
        return note

    @classmethod
    def unregister_global_hook(cls, driver_path: Path) -> str:
        """从 ~/.hermes/config.yaml 移除本插件的钩子（幂等）。返回说明文本。"""
        cmd = str(driver_path)
        if not GLOBAL_CONFIG.exists():
            return "未找到 ~/.hermes/config.yaml，无需卸载钩子。"
        try:
            import yaml
        except ImportError:
            # 无 PyYAML：仅当配置为本插件生成的最小格式（无其他内容）时可直接删除
            text = GLOBAL_CONFIG.read_text(encoding="utf-8")
            if f"command: {cmd}" not in text:
                return "~/.hermes/config.yaml 中未找到本插件钩子，无需卸载。"
            minimal = (
                "# 词趣判官 · Hermes Shell Hook（ci-pj install hermes 生成）\n"
                + _manual_hook_snippet(driver_path)
            )
            if text.strip() == minimal.strip():
                GLOBAL_CONFIG.unlink()
                return f"已删除本插件生成的钩子配置：{GLOBAL_CONFIG}"
            return (
                "未安装 PyYAML，且 ~/.hermes/config.yaml 含其他内容，无法安全改写。\n"
                f"  请手动从 {GLOBAL_CONFIG} 的 hooks.{HOOK_EVENT} 中删除指向 {cmd} 的条目。"
            )
        try:
            data = yaml.safe_load(GLOBAL_CONFIG.read_text(encoding="utf-8")) or {}
        except Exception as e:  # noqa: BLE001
            return (
                f"~/.hermes/config.yaml 解析失败（{e}），请手动检查并移除 "
                f"hooks.{HOOK_EVENT} 中指向本插件的条目。"
            )
        hooks = data.get("hooks") if isinstance(data, dict) else None
        if not isinstance(hooks, dict):
            return "~/.hermes/config.yaml 中未找到 hooks 节，无需卸载。"
        entries = hooks.get(HOOK_EVENT, [])
        if not isinstance(entries, list):
            entries = [entries]
        kept = [
            e for e in entries
            if not (isinstance(e, dict) and e.get("command") == cmd)
        ]
        removed = len(entries) - len(kept)
        if removed == 0:
            return "~/.hermes/config.yaml 中未找到本插件钩子，无需卸载。"
        if kept:
            hooks[HOOK_EVENT] = kept
        else:
            hooks.pop(HOOK_EVENT, None)
        if hooks:
            data["hooks"] = hooks
        else:
            data.pop("hooks", None)
        GLOBAL_CONFIG.write_text(_dump_yaml(data), encoding="utf-8")
        return f"已移除 {removed} 个本插件钩子；重启 Hermes 会话后生效。"

    # ---------- 卸载：精确删除本插件文件，不碰用户其他文件 ----------
    def uninstall_files(self) -> List[str]:
        removed: List[str] = []
        skill_dir = self.install_dir(None)  # ~/.hermes/skills/ci-prompt-judge
        if skill_dir.exists():
            shutil.rmtree(skill_dir)  # 整目录为本插件专有，可安全删除
            removed.append(str(skill_dir))
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

        # 1) 技能文件（Hermes 自动注册为 /ci-prompt-judge 斜杠命令）
        skill_path = d / "SKILL.md"
        skill_path.write_text(SKILL_MD, encoding="utf-8")
        created.append(str(skill_path))

        # 2) Shell Hook 驱动脚本
        driver_path = self.hook_driver_path(target)
        driver_path.parent.mkdir(parents=True, exist_ok=True)
        driver_path.write_text(HOOK_DRIVER_SH, encoding="utf-8")
        try:
            driver_path.chmod(0o755)
        except Exception:  # noqa: BLE001
            pass
        created.append(str(driver_path))

        notes = (
            "Hermes（NousResearch/hermes-agent）安装说明：\n"
            "1) 确保 ci-pj 已安装：`pip install ci-prompt-judge` 或 `pip install -e .`\n"
            f"2) 技能已写入 {d}/SKILL.md（用户级，自动注册为 /ci-prompt-judge 斜杠命令）\n"
            f"3) 钩子驱动已写入 {driver_path}\n"
        )
        if target:
            # 指定了目标目录：仅生成文件，不改动本机全局配置（便于打包/二次分发）
            notes += (
                "4) 你指定了 --target-dir，未改动本机全局配置。\n"
                f"   若要启用全局自动前置点评，请手动把以下内容合并进 "
                f"{GLOBAL_CONFIG}：\n" + _manual_hook_snippet(driver_path)
                + "   或直接运行（不带 --target-dir）：ci-pj install hermes\n"
                "   （pre_llm_call 钩子读取 stdin JSON 的 extra.user_message 字段，"
                '输出 {"context": ...} 注入本轮用户消息）\n'
            )
            return created, notes

        # 3) 默认：自动注册全局钩子
        hook_note = self.register_global_hook(driver_path)
        # 4) 非交互宿主（desktop/gateway）不弹 consent，需主动写白名单，否则钩子被静默跳过
        approval_note = _ensure_hook_allowlisted(driver_path)
        notes += (
            "4) 已自动注册 pre_llm_call Shell Hook（~/.hermes/config.yaml），"
            "每轮用户消息自动前置点评。\n"
            "5) 使用：直接对话即可自动点评；或输入 /pj-mode 渣女 等指令。\n"
            "注意：钩子仅做装饰性注入，不影响原 Prompt 执行；如不想自动评判，"
            "运行 ci-pj uninstall hermes 移除钩子（仍可手动 /pj-judge）。\n"
            "---- 钩子注册 ----\n" + hook_note + "\n"
            "---- 白名单批准 ----\n" + approval_note
        )
        return created, notes
