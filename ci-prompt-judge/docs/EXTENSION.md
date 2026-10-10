# 扩展指南

词趣判官的全部能力都由三个 JSON 资源驱动，扩展**不需要改任何 Python 代码**：

| 资源 | 包内文件（随包发布） | 用户级覆盖（推荐，升级不丢） |
|------|---------------------|---------------------------|
| 人设话术（语气包） | `core/data/speech/personas.json` | `~/.ci-pj/speech.user.json` |
| 特征规则 + 白名单 | `core/data/rule/rules.json` | `~/.ci-pj/rules.user.json` |
| 配置 + 评分权重 | `core/data/config/config.default.json` | `~/.ci-pj/config.user.json` |

- **用户级覆盖**（`~/.ci-pj/*.user.json`）：与内置文件深度合并，个人定制首选，插件升级不会冲掉你的改动。
- **改包内文件**：想给所有人提供内置新内容时用（需要发版）。改完如果装的是非编辑模式，需重新 `pip install` 让资源生效。

---

## 加一个人设（语气包）

人设 = 1 个 style 描述 + 1 个 taboo 红线 + 按规则 ID 绑定的专属台词 + 兜底台词。

### 最小可用模板

新建 `~/.ci-pj/speech.user.json`：

```json
{
  "schema_version": 1,
  "personas": {
    "毒舌产品经理": {
      "style": "犀利、一针见血、口头禅'这个需求不闭环'，毒舌但专业",
      "taboo": ["人身攻击", "侮辱"],
      "rule_speeches": {
        "R01": [
          {"text": "一句话需求就想上线？这个需求不闭环啊同学。", "weight": 2},
          {"text": "就这？用户故事三要素呢，回去补 PRD。", "weight": 1}
        ],
        "R04": [
          {"text": "技术词甩得挺专业，排期我给你压一半。", "weight": 1}
        ]
      },
      "fallback": [
        {"text": "信息不全，这需求没法评审。先说清楚目标用户是谁。", "weight": 1},
        {"text": "收到，不过这个场景我需要更多上下文，不然就是自嗨。", "weight": 1}
      ]
    }
  }
}
```

保存后（无需重启，下次命令执行时自动加载，`load_personas` 会把它合并进人设池）即可切换：

```bash
ci-pj mode 毒舌产品经理
```

`ci-pj status` 也会在「可用人设」里列出它（含用户级追加的人设）。

### 字段逐项说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `style` | ✅ | 人设的语气描述，供 LLM 理解与人工维护参考 |
| `taboo` | 建议 | 红线词列表，该人设不允许出现的内容 |
| `rule_speeches` | 建议 | **key 固定为规则 ID**（见下文 R01–R08），value 是台词数组 |
| `rule_speeches.<ID>[].text` | ✅ | 一句台词 |
| `rule_speeches.<ID>[].weight` | 建议 | 加权随机的权重（同一条规则命中时按 weight 抽一句，默认 1） |
| `fallback` | 建议 | 没命中任何规则时的兜底台词数组，同样按 `weight` 加权随机 |

**要点**：

- `rule_speeches` 不必写全 R01–R08，缺哪条就用该规则的 fallback 兜底；同名多个数组元素即"多句候选"。
- 规则 ID 对应见下表（与 `rules.json` 的 `feature_rules` 一一对应，你新增了规则就要配套新增对应 ID 的话术）：

| ID | 含义 | ID | 含义 |
|----|------|----|------|
| R01 | 超短提示词（≤15 字） | R05 | 知识提问类 |
| R02 | 文本生成类 | R07 | 超长精细提示词（>800 字） |
| R03 | AI 绘图类 | R08 | 结构化提示词 |
| R04 | 代码/运维类（白名单） | R06 | （预留，当前未使用） |

- **追加而非覆盖**：用户级文件里的人设若与内置同名，其台词会**追加**到内置台词后面（同台池加权随机）；不同名则整体新增一个人设。
- 输出格式固定为 `【<人设名>语气评判｜提示词完整性得分：<分数>/10】<台词>`，台词本身决定风味。

---

## 加一条特征规则

特征规则决定"这段 Prompt 属于什么场景"，命中的规则再去找对应人设的台词。

### 规则字段说明

规则放在 `rules.json` 的 `feature_rules` 数组中（用户级 `~/.ci-pj/rules.user.json` 也用同样结构）：

| 字段 | 说明 |
|------|------|
| `id` | 唯一 ID，建议延续 `R01`–`R99` 编号；人设话术按它绑定 |
| `name` | 规则名，人工阅读用 |
| `type` | 触发类型，四种：`length` / `keyword` / `structure` / `regex` |
| `op` + `value` | 仅 `length` 用：比较符 `<=` / `<` / `>` / `>=` 与字数阈值 |
| `keywords` | 仅 `keyword` 用：任一关键词命中即触发（不区分大小写） |
| `regex` | 仅 `regex` 用：正则表达式，命中即触发 |
| `weight` | 权重。多条规则同时命中时，**只执行权重最高者**（相同则按 ID 升序） |
| `status` | `enabled` 启用 / `disabled` 停用（改这里即可下线一条规则，不用删） |
| `tags` | 标签数组，仅用于人工分类/检索，不参与判定逻辑 |
| `whitelist` | `true` 表示命中即视为专业指令，取消短文本惩罚并抬高基础分（白名单豁免的代码依据，见 `engine.py` 判定：whitelist 节点命中 **或** 命中了该类规则） |

> `structure` 类型无参数：内置逻辑为统计结构信号（换行、编号、列表、代码块等），≥3 个即触发。

### 示例 1：关键词规则（用户级新增）

`~/.ci-pj/rules.user.json`：

```json
{
  "feature_rules": [
    {
      "id": "R09",
      "name": "翻译类",
      "type": "keyword",
      "keywords": ["翻译", "translate", "译文", "中译英", "英译中"],
      "weight": 70,
      "status": "enabled",
      "tags": ["translate"]
    }
  ]
}
```

然后在话术文件里给每个想响应的人设补上 `"R09": [{"text": "...", "weight": 1}]`，即可生效。

### 示例 2：重写一条内置规则

用户级文件里写**相同 ID** 即覆盖内置定义（按 id 合并、字段级覆盖）：

```json
{
  "feature_rules": [
    { "id": "R01", "name": "超短提示词", "type": "length", "op": "<=", "value": 8,
      "weight": 60, "status": "enabled", "tags": ["short"] }
  ]
}
```

把"超短"的阈值从 15 字收紧到 8 字；想直接关掉它，写 `{"id": "R01", "status": "disabled"}`。

---

## 调整评分权重与白名单

评分总分 1–10，由四维加权得出（`config.default.json` → `scoring.weights`）：

| 维度 | 默认权重 | 含义 |
|------|---------|------|
| `intent` | 0.30 | 有没有说清要干什么 |
| `specificity` | 0.25 | 有没有具体要求（格式/长度/约束…） |
| `structure` | 0.25 | 有没有分条、分段、代码块等结构 |
| `robustness` | 0.20 | 有没有背景/场景/输入输出说明 |

在 `~/.ci-pj/config.user.json` 里覆盖（深度合并，只写要改的键）：

```json
{
  "scoring": {
    "weights": { "intent": 0.4, "specificity": 0.2, "structure": 0.2, "robustness": 0.2 }
  }
}
```

其他常用配置键：

| 键 | 默认 | 说明 |
|----|------|------|
| `default_mode` | `激励师` | 启动人设 |
| `scoring.short_penalty_enabled` | `true` | 超短且非白名单时压低总分（软上限 4.0，见 `rules.json` 的 `scoring_rules.short_penalty_rules`） |
| `scoring.whitelist_floor` | `7.0` | 白名单命中的保底分 |
| `safety.blocklist` | `[]` | 命中即安全拦截的关键词（拦截时不评判、不放行） |
| `hook.output_format` | `json` | 钩子输出格式，`json`（上屏+注入上下文）/ `text`（旧行为） |
| `hook.lead_output` | `true` | 是否要求宿主把评判行作为回复第一行输出 |
| `command_prefix` | `/pj-` | 斜杠指令前缀 |

白名单（专业极简指令豁免）在 `rules.json` 的 `whitelist` 节点：`keywords` 关键词命中、或 `regex` 列表任一命中，即取消短文本惩罚并抬分到 `base_floor`（默认 7.0）。同样可用用户级 `rules.user.json` 深度合并追加关键词。

---

## 用户级覆盖速查

```text
~/.ci-pj/
├── config.user.json   # 覆盖配置（深度合并，只写要改的键）
├── rules.user.json    # 规则按 id 覆盖内置；scoring_rules/whitelist/conflict_resolution 深度合并
├── speech.user.json   # 人设新增；同名人设台词追加
├── state.json         # 运行状态（人设/模式），插件自动维护
└── log/               # 运行日志
```

改完用户级文件即时生效（下次命令执行时重新加载），无需重启 Agent。

## 进阶：改包内内置资源

想让人设/规则**随包发布**（给所有用户用）时，直接编辑包内文件并提 PR：

- `core/data/speech/personas.json` —— 新增 persona 节点，结构同上
- `core/data/rule/rules.json` —— `feature_rules` 增加条目，`type` 支持 `length` / `keyword` / `structure` / `regex`
- `core/data/config/config.default.json` —— 默认权重 / 模式 / 去重 / 更新频率

> 资源由 `importlib.resources` 读取，非编辑安装（`pip install .`）时需重装一次让改动进入新构建。开发态（`pip install -e .`）改完即生效。
> 高级定制可用环境变量整体替换内置资源目录：`CI_PJ_CONFIG_DIR` / `CI_PJ_RULE_DIR` / `CI_PJ_SPEECH_DIR`。

调试工具：想看一段文本到底命中了哪些规则、四维各拿多少分，用 `ci-pj diagnose "<文本>"`，输出 JSON 明细。
