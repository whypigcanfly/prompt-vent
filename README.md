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

## 🤝 贡献

欢迎提 Issue / PR，一起丰富 prompt-vent 的工具箱。

---

## 📄 许可证

各子项目许可证见其目录内的 `LICENSE` 文件（词趣判官采用 MIT）。
