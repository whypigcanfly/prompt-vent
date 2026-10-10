# 命令说明

词趣判官的命令分两层：

- **`ci-pj` CLI 命令**：装完插件后终端里直接可用的命令（所有 Agent 通用）。
- **`/pj-*` 斜杠指令**：在 Agent 对话框里输入的指令，本质是让 Agent 代为执行 `ci-pj run`。

## CLI 命令总表

| 命令 | 功能 | 示例 |
|------|------|------|
| `ci-pj run "<文本>"` | 完整处理：识别 `/pj-` 控制指令并执行，否则做前置趣味评判 | `ci-pj run "帮我写一封辞职信"` |
| `ci-pj mode <人设\|off>` | 切换人设 / 关闭插件 | `ci-pj mode 渣女` · `ci-pj mode off` |
| `ci-pj status` | 查询当前人设、模式、版本等状态 | `ci-pj status` |
| `ci-pj update [<人设>\|all]` | 联网增量更新话术（需宿主 Agent 有 WebSearch 能力） | `ci-pj update 渣女` · `ci-pj update all` |
| `ci-pj diagnose "<文本>"` | 只看特征匹配与四维评分分析，不输出评判（调试用） | `ci-pj diagnose "写一个python函数"` |
| `ci-pj hook [--prompt <文本>]` | 前置拦截钩子入口，供宿主 Agent 钩子调用（一般不手动用） | `ci-pj hook --prompt "你好"` |
| `ci-pj install <agent>` | 生成指定 Agent 的适配文件并注册钩子 | `ci-pj install claude_code` |
| `ci-pj uninstall <agent>` | 卸载指定 Agent 的钩子与生成文件（保留 `ci-pj` 核心命令） | `ci-pj uninstall claude_code` |

`<agent>` 取值：`claude_code` / `codex` / `hermes` / `workbuddy`。

`install` 还支持 `--target-dir <目录>`：仅生成适配文件到该目录，不改全局配置（便于打包分发）。

## 斜杠指令总表

在 Agent 对话框输入，结果通过 `systemMessage` 直接上屏：

| 指令 | 功能 | 示例 |
|------|------|------|
| `/pj-mode <人设\|off>` | 切换 / 关闭人设 | `/pj-mode 激励师` |
| `/pj-status` | 查询当前状态 | `/pj-status` |
| `/pj-update <人设>` / `/pj-update-all` | 联网增量更新话术 | `/pj-update 贴吧老哥` |
| `/pj-judge <文本>` | 手动评判一段 Prompt（不影响当前对话） | `/pj-judge 帮我做个网站` |

## 指令优先级

同一条输入送进 `ci-pj run` 后，按以下顺序处理（自上而下，命中即终止）：

```
安全拦截 → 话术更新指令 → 模式控制指令 → 状态查询指令 → 常规趣味评判
```

## 两种使用方式的区别

- **自动点评（钩子）**：装完即生效，每条消息都点评，你无需做任何事。`ci-pj hook` 输出 JSON（`systemMessage` 上屏点评行 + `additionalContext` 注入完整评判块），off 模式或无法提取输入时静默放行。
- **手动指令（斜杠 / CLI）**：想主动查状态、换人设、评判某段文字时用。控制指令只上屏结果，不注入模型上下文。

各 Agent 的钩子机制与生成物位置差异，见 [ADAPTERS.md](ADAPTERS.md)。
