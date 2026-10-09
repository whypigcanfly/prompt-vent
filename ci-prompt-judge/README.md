# 词趣判官 · ci-prompt-judge

> 一个**无侵入**的 Prompt 趣味前置评判插件：在大模型处理你的提示词**之前**，先做人设化趣味点评 + 1–10 分完整性评分，然后**原样放行**你的 Prompt，绝不篡改、不优化、不拦截正常任务。

本仓库是 PRD《词趣判官｜Prompt 趣味前置评判插件》的开源落地实现，按 PRD 架构规范提供**可插拔、可配置、可无限扩展**的插件内核，并附 **Claude Code / Codex / Hermes / WorkBuddy** 四类 Agent 的安装适配。

---

## 一、它解决什么

- 你写了一句很烂的 Prompt，AI 默默照做——现在有人先吐槽你一句。
- 你写了超专业的极简指令（如 `写一个python函数`），不会被误判低分（白名单豁免）。
- 你写了一篇超长结构化需求，有人先夸你一句再干活。
- 三套人设随时切换：渣女 / 激励师 / 贴吧老哥，一键开关。

**硬性约束**：永远不改你的原始 Prompt，只点评、只打分、只放行。

---

## 二、核心特性

- ✅ 三风格人设自由切换，话术可插拔、可无限扩展
- ✅ 工业级四维加权评分（意图 / 特异性 / 结构 / 鲁棒性），专业场景白名单豁免误判
- ✅ 特征规则可配置（R01–R08），支持新增任意场景规则
- ✅ 指令化控制：`/pj-mode` `/pj-status` `/pj-update` `/pj-update-all`
- ✅ 多 Agent 通用：一套内核，Claude Code / Codex / Hermes / WorkBuddy 适配
- ✅ 本地 JSON 持久化，状态跨重启/跨 Agent 不丢失
- ✅ 分级日志、去重算法、版本化配置，可直接开源迭代

---

## 三、架构（内核解耦、分层可插拔）

```
┌─────────────────────────────────────────────┐
│            接入适配层 adapter/                │  Claude Code / Codex / Hermes / WorkBuddy
│  命令文件(.md) + 前置拦截钩子(ci-pj hook)      │
└───────────────────┬─────────────────────────┘
                    │ 调用
┌───────────────────▼─────────────────────────┐
│            核心控制层 core/engine.py          │  指令调度 · 优先级 · 安全拦截 · 状态
├─────────────────────────────────────────────┤
│  业务逻辑层：rules_matcher · scoring ·         │  特征匹配 · 四维加权评分 · 话术渲染
│             speech_renderer · formatter       │
├───────────────────┬─────────────────────────┤
│  扩展能力层 service/ │ 日志 · 去重 · 联网更新   │
├───────────────────┼─────────────────────────┤
│  持久化 storage/    │ JSON(默认) / 内存 / SQLite│
└───────────────────┴─────────────────────────┘
        配置层 core/data/config · 规则层 core/data/rule · 话术层 core/data/speech
```

指令优先级（PRD 十四，自上而下）：
**安全拦截 → 话术更新 → 模式控制 → 状态查询 → 常规评判**

---

## 四、目录结构（PRD 二十二）

```
ci-prompt-judge/
├── core/        # 核心内核：engine / rules_matcher / scoring / speech_renderer / formatter
│   └── data/    # 内置资源包（随包发布，importlib.resources 读取）
│       ├── config/   # 默认配置 config.default.json（模式/权重/去重/更新/存储/日志/安全）
│       ├── rule/     # 特征规则库 + 评分规则 + 白名单 rules.json
│       └── speech/   # 角色话术库 personas.json（渣女/激励师/贴吧老哥）
├── adapter/     # 多 Agent 适配层：claude_code / codex / hermes / workbuddy / installer
├── service/     # 扩展服务：logger / dedup / update（联网增量更新）
├── storage/     # 持久化存储 store.py（JSON/内存，SQLite 可扩展）
├── skills/      # 权威 SKILL.md（WorkBuddy 技能，单一数据源）
├── log/         # 日志存储目录
├── docs/        # 文档
├── main.py      # CLI 入口（顶层模块，ci-pj 命令入口点 main:main）
├── install.sh   # 一键安装脚本
└── pyproject.toml
```

---

## 五、安装

### 方式一：一键脚本（推荐）

```bash
cd ci-prompt-judge
bash install.sh
```

脚本会安装 `ci-pj` 命令，并交互式生成目标 Agent 的适配文件。

### 方式二：手动

```bash
cd ci-prompt-judge
pip install -e .          # 提供 ci-pj 命令（可编辑安装，开发推荐）
ci-pj status              # 验证安装
```

> **打包说明**：`pyproject.toml` 已将 `main.py` 声明为 `py_modules`、并把 `config/rule/speech` 内置资源归入 `core/data/` 包（含 `package_data`）。因此**两种安装方式都可用**：
> - 可编辑安装 `pip install -e .`（开发态，源码根加入 `sys.path`）；
> - 普通/ wheel 安装 `pip install .` 或 `pip install ci-prompt-judge`（资源随 `core.data` 包发布，由 `importlib.resources` 读取，不再依赖源码布局）。
> 仍可通过环境变量 `CI_PJ_CONFIG_DIR` / `CI_PJ_RULE_DIR` / `CI_PJ_SPEECH_DIR` 覆盖内置资源目录。

---

## 六、接入到你的 Agent

```bash
# 生成对应 Agent 的适配文件（命令文件 + 钩子片段 + 技能）
ci-pj install claude_code
ci-pj install codex
ci-pj install hermes
ci-pj install workbuddy
```

| Agent | 命令文件位置 | 前置拦截 |
|-------|-------------|----------|
| Claude Code | `.claude/commands/pj-*.md` + 合并 `settings.json` 的 `UserPromptSubmit` 钩子 | `ci-pj hook` 读取 stdin |
| Codex | `.codex/commands/pj-*.md`（按版本核对） | 注册 PreTool/UserPrompt 钩子 |
| Hermes | `.hermes/commands/pj-*.md` | 输入预处理挂载 `ci-pj hook` |
| WorkBuddy | `~/.workbuddy/skills/ci-prompt-judge/SKILL.md` | **安装时自动注册**全局 `UserPromptSubmit` 钩子（每次提交消息自动点评） |

> 钩子仅做**装饰性输出**，不影响原 Prompt 执行；不想自动点评时删除钩子即可，仍可手动 `/pj-judge`。

### WorkBuddy 自动注册全局钩子（重点）

`ci-pj install workbuddy` 会做三件事：

1. 把技能 `SKILL.md` 写入 `~/.workbuddy/skills/ci-prompt-judge/`（用户级，全项目可用）；
2. 写入钩子驱动脚本 `hook_driver.sh`；
3. **自动把 `UserPromptSubmit` 钩子合并进 `~/.workbuddy/settings.json`**（带时间戳备份、幂等去重）。

这样**每次你在 WorkBuddy 提交消息，都会先自动运行 `ci-pj hook` 做趣味前置点评**，无需在当前对话显式触发，也不再依赖「技能被 agent 主动调用」。重启 WorkBuddy 后生效。

- 卸载：`ci-pj uninstall workbuddy`（移除钩子 + 删除技能目录，保留核心包）。
- `ci-pj hook` 已支持解析钩子传入的 JSON 事件（提取 `prompt` 字段），也兼容手动 `ci-pj hook --prompt "..."` 或管道纯文本。

---

## 七、使用

```bash
ci-pj mode 渣女            # 切换为渣女人设
ci-pj mode off             # 完全关闭插件（无任何输出）
ci-pj status               # 查询当前状态
ci-pj run "帮我写一封辞职信"   # 对一段 Prompt 做趣味评判
ci-pj diagnose "你的提示词"    # 仅看匹配与评分分析（不输出评判）
ci-pj update 渣女          # 联网增量更新话术（需宿主 WebSearch）
```

评判输出（强制格式）：

```
【渣女语气评判｜提示词完整性得分：6.8/10】又要我帮你写东西啦？行吧行吧，谁让我心软呢，说清楚点我才写得动。
---放行提示词---
帮我写一封体面的辞职信，语气要正式，分三段，第一段感谢，第二段说明原因，第三段祝福
```

---

## 八、评分说明

四维加权（默认权重，可在 `core/data/config/config.default.json` 调整）：
**意图 30% / 特异性 25% / 结构 25% / 鲁棒性 20%**，总分 1–10。

- **超短且非专业**的提示词会被软上限压低（避免敷衍被误判高分）。
- **专业极简指令**（代码 / CLI / 运维等）命中白名单，取消短文本惩罚并拉高基础分（PRD 十七）。
- 完全空泛 / 极短的纯闲聊会落在低分区，属预期行为。

---

## 九、扩展开发（零侵入）

### 加一个人设

在 `core/data/speech/personas.json` 增加一个 persona 节点，配置 `style` / `taboo` / `rule_speeches`（按规则 ID 绑定）/ `fallback` 即可，无需改代码。

### 加一条特征规则

在 `core/data/rule/rules.json` 的 `feature_rules` 增加一条（`id` / `type` / `weight` / `status`），`type` 支持 `length` / `keyword` / `structure` / `regex`。

### 调整评分权重

改 `core/data/config/config.default.json` 的 `scoring.weights`，实时生效。

---

## 十、许可证

MIT © ci-prompt-judge contributors

> 需求来源：《词趣判官｜Prompt 趣味前置评判插件 · 详细需求文档（PRD）》。本实现按 PRD 的架构与功能规范落地，并补充了可运行的工程细节。
