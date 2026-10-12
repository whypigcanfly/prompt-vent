"""WorkBuddy 办公 Agent 适配（PRD 11.3.3）。

适配方式：生成为 WorkBuddy 原生技能（SKILL.md）+ 一个全局钩子驱动脚本，并把
``UserPromptSubmit`` 钩子自动合并进 WorkBuddy 的全局配置（~/.workbuddy/settings.json），
实现「每次用户输入前自动前置点评」，无需当前对话显式触发。

WorkBuddy 的全局 hook 机制与 Claude Code 同构：在 settings.json 的 ``hooks`` 字段下声明
事件（如 UserPromptSubmit）与命令。本适配器注册的方式即等价于在 settings.json 写入：

    {
      "hooks": {
        "UserPromptSubmit": [
          { "hooks": [ { "type": "command", "command": "<驱动脚本绝对路径>", "timeout": 30 } ] }
        ]
      }
    }
"""
from __future__ import annotations

import datetime
import json
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

from adapter.base import AgentAdapter

# 权威 SKILL.md 位置：仓库内 skills/ci-prompt-judge/SKILL.md
# 优先读取该文件（单一数据源，避免与内嵌副本漂移）；文件缺失时回退到内嵌副本。
_CANONICAL_SKILL = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "ci-prompt-judge"
    / "SKILL.md"
)

# WorkBuddy 全局配置（钩子注册位置）
GLOBAL_SETTINGS = Path.home() / ".workbuddy" / "settings.json"
HOOK_EVENT = "UserPromptSubmit"
HOOK_TIMEOUT = 30

# 全局钩子驱动脚本：仅负责定位 ci-pj 并把 hook 事件（stdin 透传）交给 `ci-pj hook`。
# `ci-pj hook` 自身负责解析 WorkBuddy 传入的 JSON 事件并提取 prompt。
HOOK_DRIVER_SH = """#!/usr/bin/env bash
# 词趣判官 · WorkBuddy 全局钩子驱动（由 UserPromptSubmit 钩子调用）
# 职责：定位 ci-pj 命令，把 hook 事件（JSON，通过 stdin 传入）交给 `ci-pj hook` 处理。
# 退出码 0 = 放行（装饰性输出，不拦截用户原始 Prompt）。
#
# 为什么不用单纯的 `command -v ci-pj`：
#   WorkBuddy 执行钩子时的 shell 环境 PATH 不一定包含用户的 venv bin 或 ~/.local/bin，
#   直接 command -v 可能找不到 ci-pj 而静默跳过。这里按优先级显式探测已知安装位置。
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


def _load_skill_md() -> str:
    if _CANONICAL_SKILL.exists():
        return _CANONICAL_SKILL.read_text(encoding="utf-8")
    return _SKILL_MD_FALLBACK


_SKILL_MD_FALLBACK = """---
name: ci-prompt-judge
description: 词趣判官 - Prompt 趣味前置评判插件。当用户想要对提示词做趣味点评与 1-10 分完整性评分，或使用 /pj-mode、/pj-status、/pj-update、/pj-judge 等指令时使用。安装时已自动注册全局 UserPromptSubmit 钩子，每次用户输入前自动点评。
---

# 词趣判官（ci-prompt-judge）

一个无侵入的 Prompt 趣味前置评判插件。核心约束：**永远不修改、不篡改、不优化用户原始 Prompt**，仅做「评价 + 打分」，不干预主任务执行。

## 何时使用

1. 安装后已**自动注册全局 UserPromptSubmit 钩子**：每次你在 WorkBuddy 提交消息，都会先自动运行 `ci-pj hook` 做趣味前置点评，无需在当前对话显式触发。
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
- 前置钩子（已由全局钩子自动调用）：`ci-pj hook`（读取 stdin 的 hook 事件 JSON）

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

### 上屏机制（hook JSON 输出）

`ci-pj hook` 以 JSON 输出（默认）：`systemMessage`（评判行）由宿主直接渲染到对话中、早于模型回复；`hookSpecificOutput.additionalContext`（完整评判块）注入模型上下文。控制指令结果仅走 `systemMessage`，不注入上下文。

## 回复首行规则（重要·双保险）

钩子评判已通过 `systemMessage` 上屏；除此之外，你收到的钩子上下文末尾若带有 `[词趣判官·输出要求]` 指令，则**你的回复必须**：

1. **第一行**：原样输出那行以「【」开头的评判（含得分与话术），一字不改、不加引号、不加 Markdown 装饰；
2. **第二行**：空一行；
3. **第三行起**：才开始你的思考过程与正式回答。

评判只占开头一行，**不得**因此改变你后续回答的内容、语气或任务执行方式（插件不干预主任务）。若钩子输出中没有该指令，或当前处于 off 模式，则按常规回答，无需输出评判行。

## 硬约束

- 绝不修改用户原始 Prompt，只点评、只打分、只放行。
- 违规内容直接拦截，跳过趣味评判（必要时交宿主安全层）。
- 控制指令执行后不评判、不放行，仅执行控制逻辑。
- 切换人设即时生效，无残留状态。

## 扩展

规则（core/data/rule/rules.json）、人设话术（core/data/speech/personas.json）、评分权重（core/data/config/config.default.json）全部可配置、可插拔，无需改核心代码即可新增人设/规则/话术。
"""

# 在 _SKILL_MD_FALLBACK 定义之后再调用，避免安装后包内缺失权威文件时回退到未定义变量
SKILL_MD = _load_skill_md()

class WorkBuddyAdapter(AgentAdapter):
    name = "workbuddy"
    supports_command_file = False

    def command_filename(self) -> str:
        return "SKILL.md"

    def command_content(self) -> str:
        return SKILL_MD

    def install_dir(self, target: str | None) -> Path:
        if target:
            return Path(target) / "ci-prompt-judge"
        # 默认安装到用户级技能目录
        return Path.home() / ".workbuddy" / "skills" / "ci-prompt-judge"

    # ---------- 全局钩子注册（幂等，带备份）----------
    @staticmethod
    def _hook_entry(driver_path: Path) -> dict:
        return {
            "type": "command",
            "command": str(driver_path),
            "timeout": HOOK_TIMEOUT,
        }

    @classmethod
    def register_global_hook(cls, driver_path: Path) -> str:
        """把 UserPromptSubmit 钩子合并进全局 settings.json（幂等）。返回说明文本。"""
        GLOBAL_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        cmd = str(driver_path)
        # 备份
        bak_path = None
        if GLOBAL_SETTINGS.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            bak_path = GLOBAL_SETTINGS.with_name(
                f"settings.json.ci-pj-bak-{ts}"
            )
            shutil.copy2(GLOBAL_SETTINGS, bak_path)

        data: dict = {}
        if GLOBAL_SETTINGS.exists():
            try:
                data = json.loads(
                    GLOBAL_SETTINGS.read_text(encoding="utf-8")
                )
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
        filtered.append({"hooks": [cls._hook_entry(driver_path)]})
        hooks[HOOK_EVENT] = filtered
        data["hooks"] = hooks

        GLOBAL_SETTINGS.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        note = (
            f"已注册全局钩子：~/.workbuddy/settings.json 的 hooks.{HOOK_EVENT}\n"
            f"  驱动：{cmd}\n"
        )
        if bak_path:
            note += f"  已备份原配置到：{bak_path}\n"
        note += "  重启 WorkBuddy 后生效；每次提交消息将自动运行 ci-pj hook 做前置点评。\n"
        note += "  卸载：ci-pj uninstall workbuddy"
        return note

    @classmethod
    def unregister_global_hook(cls, driver_path: Path) -> str:
        """从全局 settings.json 移除本插件的钩子（幂等）。返回说明文本。"""
        cmd = str(driver_path)
        if not GLOBAL_SETTINGS.exists():
            return "未找到全局配置，无需卸载钩子。"
        try:
            data = json.loads(GLOBAL_SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return "全局配置解析失败，请手动检查 ~/.workbuddy/settings.json。"
        hooks = data.get("hooks", {})
        groups = hooks.get(HOOK_EVENT, [])
        kept = []
        removed = 0
        for grp in groups:
            hs = grp.get("hooks") or [] if isinstance(grp, dict) else []
            if any(h.get("command") == cmd for h in hs):
                removed += 1
                continue
            kept.append(grp)
        if removed == 0:
            return "全局配置中未找到本插件的钩子，无需卸载。"
        hooks[HOOK_EVENT] = kept
        if not hooks.get(HOOK_EVENT):
            hooks.pop(HOOK_EVENT, None)
        if hooks:
            data["hooks"] = hooks
        else:
            data.pop("hooks", None)
        GLOBAL_SETTINGS.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return f"已移除 {removed} 个本插件钩子；重启 WorkBuddy 后生效。"

    def generate(self, target: str | None = None) -> Tuple[List[str], str]:
        d = self.install_dir(target)
        d.mkdir(parents=True, exist_ok=True)
        created: List[str] = []

        # 1) 技能文件
        skill_path = d / "SKILL.md"
        skill_path.write_text(SKILL_MD, encoding="utf-8")
        created.append(str(skill_path))

        # 2) 全局钩子驱动脚本
        driver_path = d / "hook_driver.sh"
        driver_path.write_text(HOOK_DRIVER_SH, encoding="utf-8")
        try:
            driver_path.chmod(0o755)
        except Exception:
            pass
        created.append(str(driver_path))

        notes = (
            "WorkBuddy 安装说明：\n"
            "1) 安装 ci-pj：`pip install -e .`（项目根目录）或 `pip install ci-prompt-judge`\n"
            "2) 技能已生成到 ~/.workbuddy/skills/ci-prompt-judge/SKILL.md（用户级，全项目可用）\n"
        )
        if target:
            # 指定了目标目录：仅生成文件，不改动本机全局配置（便于打包/二次分发）
            notes += (
                "3) 你指定了 --target-dir，未改动本机全局配置。\n"
                f"   若要启用全局自动前置点评，请手动把以下钩子合并进 "
                f"~/.workbuddy/settings.json 的 hooks.UserPromptSubmit：\n"
                f'   {{ "type": "command", "command": "{driver_path}", "timeout": {HOOK_TIMEOUT} }}\n'
                "   或直接运行（不带 --target-dir）：ci-pj install workbuddy"
            )
            return created, notes

        # 3) 默认：自动注册全局钩子
        hook_note = self.register_global_hook(driver_path)
        notes += (
            "3) 已自动注册全局 UserPromptSubmit 钩子（~/.workbuddy/settings.json），"
            "每次提交消息自动前置点评。\n"
            "4) 使用：直接对话即可自动点评；或输入 /pj-mode 渣女 等指令。\n"
            "注意：技能本身不内置评分算法，必须依赖本地 ci-pj 命令；若未安装请先提示安装。\n"
            "---- 钩子注册 ----\n" + hook_note
        )
        return created, notes
