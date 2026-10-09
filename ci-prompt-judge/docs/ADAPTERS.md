# 各 Agent 接入细则

`ci-pj install <agent>` 会生成对应平台的命令文件与钩子片段。下面是人工落地时需要知道的关键点。

## Claude Code

生成物：
- `.claude/commands/pj-mode.md` `pj-status.md` `pj-update.md` `pj-judge.md`
- `.claude/settings.ci-pj.hook.json`（钩子片段，需合并进现有 `settings.json`）

**命令文件内容示例**（`pj-mode.md`）：
```markdown
---
description: 词趣判官 - 切换/关闭人设
---
!ci-pj run "$ARGUMENTS"
```

**钩子合并**：把下面 `hooks` 节点并入 `~/.claude/settings.json`（项目级放 `.claude/settings.json`）：
```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "ci-pj hook" } ] }
    ]
  }
}
```
说明：`UserPromptSubmit` 钩子会把用户输入以 JSON 形式通过 stdin 传入，`ci-pj hook` 读取其中的 `prompt` 字段并输出趣味评判（装饰性、非阻塞）。控制指令（/pj-*）建议走 slash 命令，避免被当作普通任务。

## Codex

生成物：`.codex/commands/pj-*.md`。不同 Codex 版本命令目录/钩子机制可能不同，请按所用版本核对；若版本不支持命令文件，可在 `AGENTS.md` / 系统提示中声明：「用户以 `/pj-` 开头的输入交给 `ci-pj` 处理；其余输入先运行 `ci-pj hook` 再做回答」。

## Hermes

生成物：`.hermes/commands/pj-*.md`。在输入预处理环节挂载 `ci-pj hook` 即可实现多轮连续评判；状态存于 `~/.ci-pj/state.json`，跨轮切换人设不串模。

## WorkBuddy

生成物：`~/.workbuddy/skills/ci-prompt-judge/SKILL.md`（用户级）。该技能声明：用户使用 `/pj-` 指令或对提示词求点评分时调用 `ci-pj`；也可在 WorkBuddy 钩子中注册 `ci-pj hook` 实现自动前置点评。技能本身不内置算法，依赖本地 `ci-pj` 命令。
