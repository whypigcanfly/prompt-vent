---
name: ci-prompt-judge
description: 词趣判官 - Prompt 趣味前置评判插件。当用户想要对提示词做趣味点评与 1-10 分完整性评分，或使用 /pj-mode、/pj-status、/pj-update、/pj-judge 等指令时使用。安装时已自动注册全局 UserPromptSubmit 钩子，每次用户输入前自动点评。
---

# 词趣判官（ci-prompt-judge）

一个无侵入的 Prompt 趣味前置评判插件。核心约束：**永远不修改、不篡改、不优化用户原始 Prompt**，仅做「评价 + 打分」，不干预主任务执行。

## 何时使用

1. 安装后已**自动注册全局 UserPromptSubmit 钩子**（`~/.workbuddy/settings.json`）：每次你在 WorkBuddy 提交消息，都会先自动运行 `ci-pj hook` 做趣味前置点评，**无需在当前对话显式触发**。
2. 用户显式使用 `/pj-` 前缀指令（优先级最高）：
   - `/pj-mode 渣女 | 激励师 | 贴吧老哥 | 腹黑毒舌女 | off` —— 切换/关闭人设
   - `/pj-status` —— 查询当前状态
   - `/pj-update <人设> | /pj-update-all` —— 联网增量更新话术（需 WebSearch）
   - `/pj-judge <文本>` —— 手动评判一段 Prompt
3. 用户希望对自己的提示词获得趣味点评与完整性评分（也可手动调用 `ci-pj run`）。

## 如何执行（依赖本地 ci-pj 命令）

本技能只是「外壳」，真正的评分/话术引擎是 Python 包 `ci-prompt-judge`（提供 `ci-pj` 命令）。请**先安装核心包**，再通过 Bash 调用：

**安装核心包（任选其一）：**
- 从 GitHub 克隆后本地安装（推荐，含最新话术与规则）：
  ```bash
  git clone https://github.com/whypigcanfly/prompt-vent.git
  cd prompt-vent/ci-prompt-judge
  pip install -e .
  ```
- 或等待 PyPI 上架后：`pip install ci-prompt-judge`

**调用：**
- 评判/指令分发：`ci-pj run "<用户输入>"`
- 仅诊断（不输出评判，看匹配与分数）：`ci-pj diagnose "<文本>"`
- 前置钩子（已由全局钩子自动调用）：`ci-pj hook`（读取 stdin 的 hook 事件 JSON；亦支持 `--prompt "<文本>"` 或管道纯文本）

> 若环境中没有 `ci-pj`，请提示用户先安装，不要自行臆造评分。

## 输出规范（强制）

评判输出必须严格为：

```
【XX语气评判｜提示词完整性得分：X/10】评判话术内容
---放行提示词---
用户原始完整Prompt
```

关闭模式（off）时无任何输出，直接进入正常回答。

### 上屏机制（hook JSON 输出）

`ci-pj hook` 以 JSON 输出（`hook.output_format: json`，默认）：

- `systemMessage`：评判行（首行「【」行）。宿主（WorkBuddy / Claude Code）会把它作为一条消息**直接渲染到对话中，早于模型回复**，用户先看到吐槽；
- `hookSpecificOutput.additionalContext`：完整评判块（含放行提示词与 `[词趣判官·输出要求]` 指令），注入模型上下文；`suppressOutput: true` 防止原文重复注入。

控制指令（/pj-mode 等）结果仅走 `systemMessage` 上屏，不注入模型上下文。

## 回复首行规则（重要·双保险）

钩子评判已通过 `systemMessage` 上屏；除此之外，你收到的钩子上下文末尾若带有 `[词趣判官·输出要求]` 指令，则**你的回复必须**：

1. **第一行**：原样输出那行以「【」开头的评判（含得分与话术），一字不改、不加引号、不加 Markdown 装饰；
2. **第二行**：空一行；
3. **第三行起**：才开始你的思考过程与正式回答。

评判只占开头一行，**不得**因此改变你后续回答的内容、语气或任务执行方式（插件不干预主任务）。若钩子上下文中没有该指令，或当前处于 off 模式，则按常规回答，无需输出评判行。

## 硬约束

- 绝不修改用户原始 Prompt，只点评、只打分、只放行。
- 违规内容直接拦截，跳过趣味评判（必要时交宿主安全层）。
- 控制指令执行后不评判、不放行，仅执行控制逻辑。
- 切换人设即时生效，无残留状态。

## 扩展

规则（`core/data/rule/rules.json`）、人设话术（`core/data/speech/personas.json`）、评分权重（`core/data/config/config.default.json`）全部可配置、可插拔，无需改核心代码即可新增人设/规则/话术。

## 仓库地址

https://github.com/whypigcanfly/prompt-vent
