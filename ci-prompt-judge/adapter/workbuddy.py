"""WorkBuddy 办公 Agent 适配（PRD 11.3.3）。

适配方式：生成为 WorkBuddy 原生技能（SKILL.md）。
- 技能内声明：用户以 /pj- 开头的输入交 ci-pj 处理；其余输入可先运行 ci-pj hook 做趣味评判再回答
- 也可在 WorkBuddy 的钩子（hook）系统中注册 `ci-pj hook` 实现自动前置拦截
- 话术适配办公场景语境，兼顾趣味与实用性
"""
from __future__ import annotations

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


def _load_skill_md() -> str:
    if _CANONICAL_SKILL.exists():
        return _CANONICAL_SKILL.read_text(encoding="utf-8")
    return _SKILL_MD_FALLBACK


SKILL_MD = _load_skill_md()

_SKILL_MD_FALLBACK = """---
name: ci-prompt-judge
description: 词趣判官 - Prompt 趣味前置评判插件。当用户想要对提示词做趣味点评与 1-10 分完整性评分，或使用 /pj-mode、/pj-status、/pj-update、/pj-judge 等指令时使用。也可作为每次对话的前置装饰层，先点评再放行原 Prompt。
---

# 词趣判官（ci-prompt-judge）

一个无侵入的 Prompt 趣味前置评判插件。核心约束：**永远不修改、不篡改、不优化用户原始 Prompt**，仅做「评价 + 打分」，不干预主任务执行。

## 何时使用

1. 用户显式使用 `/pj-` 前缀指令（优先级最高）：
   - `/pj-mode 渣女 | 激励师 | 贴吧老哥 | off` —— 切换/关闭人设
   - `/pj-status` —— 查询当前状态
   - `/pj-update <人设> | /pj-update-all` —— 联网增量更新话术（需 WebSearch）
   - `/pj-judge <文本>` —— 手动评判一段 Prompt
2. 用户希望对自己的提示词获得趣味点评与完整性评分。
3. （可选）作为前置装饰层：每次用户输入后，先运行 `ci-pj hook` 输出趣味评判，再照常回答。

## 如何执行

本技能依赖已安装的 `ci-pj` 命令行工具（Python）。请通过 Bash 调用：

- 评判/指令分发：`ci-pj run "<用户输入>"`
- 仅诊断（不输出评判，看匹配与分数）：`ci-pj diagnose "<文本>"`
- 前置钩子：`ci-pj hook --prompt "<文本>"`（或管道读 stdin）

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

## 硬约束

- 绝不修改用户原始 Prompt，只点评、只打分、只放行。
- 违规内容直接拦截，跳过趣味评判（必要时交宿主安全层）。
- 控制指令执行后不评判、不放行，仅执行控制逻辑。
- 切换人设即时生效，无残留状态。

## 扩展

规则（core/data/rule/rules.json）、人设话术（core/data/speech/personas.json）、评分权重（core/data/config/config.default.json）全部可配置、可插拔，无需改核心代码即可新增人设/规则/话术。
"""


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

    def generate(self, target: str | None = None) -> Tuple[List[str], str]:
        d = self.install_dir(target)
        d.mkdir(parents=True, exist_ok=True)
        skill_path = d / "SKILL.md"
        skill_path.write_text(SKILL_MD, encoding="utf-8")
        created = [str(skill_path)]
        notes = (
            "WorkBuddy 安装说明：\n"
            "1) 安装 ci-pj：`pip install -e .`（项目根目录）\n"
            "2) 技能已生成到 ~/.workbuddy/skills/ci-prompt-judge/SKILL.md（用户级，全项目可用）\n"
            "   也可将整个 ci-prompt-judge 项目放到项目级 .workbuddy/skills/ 下\n"
            "3) 自动前置拦截（可选）：在 WorkBuddy 钩子（hook）中注册 `ci-pj hook`，每次输入后自动点评\n"
            "4) 使用：用户说「评判一下我的提示词」或输入 /pj-mode 渣女 等，按技能说明调用 ci-pj。\n"
            "注意：技能本身不内置评分算法，必须依赖本地 ci-pj 命令；若未安装请先提示安装。"
        )
        return created, notes
