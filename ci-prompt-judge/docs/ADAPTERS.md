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

## Hermes（NousResearch/hermes-agent）

生成物（`ci-pj install hermes`，用户级）：
- `~/.hermes/skills/ci-prompt-judge/SKILL.md` —— 技能文件，Hermes 自动注册为 `/ci-prompt-judge` 斜杠命令（agentskills.io 开放标准）
- `~/.hermes/agent-hooks/ci-pj-hook.sh` —— Shell Hook 驱动脚本（探测 ci-pj 安装位置，stdin 透传事件）
- `~/.hermes/config.yaml` 的 `hooks.pre_llm_call` 条目（自动合并，带时间戳备份、幂等去重）

**钩子机制**（官方文档 [Hooks 参考](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)）：每轮用户消息进入 LLM 前，Hermes 以子进程运行驱动脚本，stdin 传入 JSON 事件（用户输入在 `extra.user_message`）；脚本 stdout 返回 `{"context": "..."}` 会被注入本轮用户消息，`ci-pj hook` 已适配该事件并输出此格式（off 模式 / 控制指令静默 no-op）。

注意事项：
- 首次触发时 Hermes 会按 `(event, command)` 弹一次确认；可在 config.yaml 设 `hooks_auto_accept: true` 跳过
- 验证：`hermes hooks test pre_llm_call`；查看：`hermes hooks list`
- 自动改写 config.yaml 需要 PyYAML（缺失时降级为打印手动合并片段）；改写会丢失 YAML 注释（有备份可找回）
- 多轮状态存于 `~/.ci-pj/state.json`，跨轮切换人设不串模
- 卸载：`ci-pj uninstall hermes`（移除钩子条目 + 删除技能目录与驱动脚本）

## WorkBuddy

生成物：`~/.workbuddy/skills/ci-prompt-judge/SKILL.md`（用户级）。该技能声明：用户使用 `/pj-` 指令或对提示词求点评分时调用 `ci-pj`；也可在 WorkBuddy 钩子中注册 `ci-pj hook` 实现自动前置点评。技能本身不内置算法，依赖本地 `ci-pj` 命令。
