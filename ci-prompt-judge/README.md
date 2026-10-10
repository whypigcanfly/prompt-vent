# 词趣判官 · ci-prompt-judge

一个**无侵入**的 Prompt 趣味前置评判插件：在大模型处理你的提示词**之前**，先做人设化趣味点评 + 1–10 分完整性评分，然后**原样放行**你的 Prompt，绝不篡改、不优化、不拦截正常任务。

三套人设随时切换：**渣女 / 激励师 / 贴吧老哥**。

## 效果预览

你提交一句 `帮我写一封辞职信`，AI 回答之前会先收到一句点评：

```
【渣女语气评判｜提示词完整性得分：6.8/10】又要我帮你写东西啦？行吧行吧，谁让我心软呢，说清楚点我才写得动。
---放行提示词---
帮我写一封辞职信
```

你的原始 Prompt 原样进入主流程，该干嘛干嘛。

## 快速开始

**第 1 步：安装**（以 Claude Code 为例，一行命令，无需 clone）：

```bash
curl -fsSL https://raw.githubusercontent.com/whypigcanfly/prompt-vent/main/ci-prompt-judge/install.sh | bash -s -- claude_code
```

把 `claude_code` 换成 `codex` / `hermes` / `workbuddy` 即可安装到其他 Agent。

脚本会自动：安装 `ci-pj` 命令 → 生成适配文件 → 注册全局钩子。**重启对应 Agent** 后生效。

**第 2 步：什么都不做**。之后每次提交消息，都会先自动收到一句人设点评 + 评分，然后正常干活。

**第 3 步（可选）：换个口味**。在 Agent 对话里直接输入：

```text
/pj-mode 渣女       # 换人设：渣女 / 激励师 / 贴吧老哥
/pj-mode off        # 完全闭嘴（不再输出任何点评）
/pj-status          # 看看当前是什么状态
```

不想要自动点评了？`ci-pj uninstall claude_code` 一键卸载，或临时用 `/pj-mode off` 关闭。

> 本地开发安装：`cd ci-prompt-judge && pip install -e .`，再 `ci-pj install <agent>`。详见 [docs/COMMANDS.md](docs/COMMANDS.md)。

## 它解决什么

- 你写了一句很烂的 Prompt，AI 默默照做——现在有人先吐槽你一句。
- 你写了超专业的极简指令（如 `写一个python函数`），不会被误判低分（白名单豁免）。
- 你写了一篇超长结构化需求，有人先夸你一句再干活。

**硬性约束**：永远不改你的原始 Prompt，只点评、只打分、只放行。

## 它是怎么工作的

安装时在宿主 Agent 注册了一个 `UserPromptSubmit` 前置钩子：每条消息先经过 `ci-pj hook` 做特征匹配 → 四维加权评分（意图 / 特异性 / 结构 / 鲁棒性，总分 1–10）→ 按当前人设渲染一句点评，随后原样放行。

| Agent | 命令触发方式 | 自动点评 |
|-------|-------------|---------|
| Claude Code | `/pj-*` 斜杠命令 | ✅ 全局钩子自动注册 |
| WorkBuddy | `/pj-*` 斜杠命令 | ✅ 全局钩子自动注册 |
| Hermes | `/ci-prompt-judge` 技能命令 | ✅ Shell Hook `pre_llm_call` 自动注册 |
| Codex | `.codex/commands/pj-*.md` | 按版本核对，可退化为 AGENTS.md 声明 |

各 Agent 生成物位置与钩子细节见 [docs/ADAPTERS.md](docs/ADAPTERS.md)。

## 深入了解

| 想做什么 | 看哪里 |
|---------|-------|
| 全部命令说明（CLI + 斜杠指令） | [docs/COMMANDS.md](docs/COMMANDS.md) |
| 加一个人设 / 语气包 | [docs/EXTENSION.md · 加一个人设](docs/EXTENSION.md#加一个人设语气包) |
| 新增 / 重写特征规则 | [docs/EXTENSION.md · 加一条特征规则](docs/EXTENSION.md#加一条特征规则) |
| 调整评分权重、白名单 | [docs/EXTENSION.md · 调整评分](docs/EXTENSION.md#调整评分权重与白名单) |
| 不改包内文件，只做个人覆盖 | [docs/EXTENSION.md · 用户级覆盖](docs/EXTENSION.md#用户级覆盖速查) |

## 目录结构

```
ci-prompt-judge/
├── core/        # 核心内核：engine / rules_matcher / scoring / speech_renderer / formatter
│   └── data/    # 内置资源包：config/ 默认配置 · rule/ 特征规则 · speech/ 人设话术
├── adapter/     # 多 Agent 适配层：claude_code / codex / hermes / workbuddy / installer
├── service/     # 扩展服务：logger / dedup / update（联网增量更新）
├── storage/     # 持久化存储（JSON / 内存，SQLite 可扩展）
├── skills/      # 权威 SKILL.md（WorkBuddy 技能，单一数据源）
├── docs/        # 文档：命令说明 / 扩展指南 / 各 Agent 接入细则
├── main.py      # CLI 入口（ci-pj 命令）
├── install.sh   # 一键安装脚本
└── pyproject.toml
```

## 许可证

MIT © ci-prompt-judge contributors

> 需求来源：《词趣判官｜Prompt 趣味前置评判插件 · 详细需求文档（PRD）》。本实现按 PRD 的架构与功能规范落地，并补充了可运行的工程细节。
