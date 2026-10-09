# prompt-vent

> 一个面向 AI Agent 的「提示词（Prompt）周边」开源工具箱。

名字取自 **vent**（出气口 / 通风孔）—— 把和 AI 打交道时那些琐碎、重复、又很好玩的小工具，都汇集到这里通风透气。

---

## 🧩 子项目一览

| 子项目 | 简介 | 状态 | 文档 |
| --- | --- | --- | --- |
| [ci-prompt-judge · 词趣判官](./ci-prompt-judge) | 前置拦截式 Prompt 趣味评判插件：在 AI 处理用户输入**之前**，先做特征识别、人设化趣味评语、1–10 分打分，再放行原 Prompt。支持 Claude Code / Codex / Hermes / WorkBuddy 等多 Agent 一键安装。 | ✅ 可用 | [README](./ci-prompt-judge/README.md) |

> 更多「提示词周边」小工具会持续补充到本仓库。

---

## 🚀 快速开始（以词趣判官为例）

```bash
git clone https://github.com/whypigcanfly/prompt-vent.git
cd prompt-vent/ci-prompt-judge
pip install -e .
ci-pj mode 渣女            # 切换人设：渣女 / 激励师 / 贴吧老哥
ci-pj run "帮我写一封体面的辞职信"
```

---

## 🔌 在 WorkBuddy 中安装词趣判官

词趣判官已提供 WorkBuddy 原生技能（仓库内 `ci-prompt-judge/skills/ci-prompt-judge/SKILL.md`）。安装方式任选其一：

**方式一：通过 URL 导入（图形界面，最省事）**
1. 打开 WorkBuddy → 左侧「技能」面板（或 设置 → 技能管理）。
2. 选择 **「通过 URL 导入 / Import from URL」**。
3. 填入仓库地址 `https://github.com/whypigcanfly/prompt-vent`，确认自动拉取。
4. 在技能管理面板确认「词趣判官（ci-prompt-judge）」已**启用**。

**方式二：手动放置 / 命令行生成**
- 用户级（所有项目可用）：把技能目录放到 `~/.workbuddy/skills/ci-prompt-judge/`
- 项目级（团队共享）：放到 `<你的项目>/.workbuddy/skills/ci-prompt-judge/`
- 或克隆仓库后执行：`ci-pj install workbuddy`（自动写入用户级技能目录）。

> ⚠️ 技能只是「外壳」，真正的评分引擎是 Python 包 `ci-prompt-judge`。无论哪种方式，**都必须先安装核心包**：
> ```bash
> git clone https://github.com/whypigcanfly/prompt-vent.git
> cd prompt-vent/ci-prompt-judge && pip install -e .
> ```
> 安装后用户说「评判一下我的提示词」或输入 `/pj-mode 渣女` 即可触发。

---

## 🤝 贡献

欢迎提 Issue / PR，一起丰富 prompt-vent 的工具箱。

---

## 📄 许可证

各子项目许可证见其目录内的 `LICENSE` 文件（词趣判官采用 MIT）。
