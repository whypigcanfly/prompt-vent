#!/usr/bin/env python3
"""词趣判官 CLI 入口（PRD 二十二 main.py）。

子命令：
  run "<文本>"            完整处理：识别 /pj- 控制指令并执行，否则做前置趣味评判
  mode <渣女|激励师|贴吧老哥|off>   切换/关闭插件
  status                  查询当前状态
  update [<人设>|all]     触发联网话术增量更新（需宿主 WebSearch 支持）
  diagnose "<文本>"       仅返回匹配/评分分析（不输出评判），便于调试
  hook [--prompt <文本>]  前置拦截钩子入口（供 Agent 适配层调用）
  install <agent>         安装到指定 Agent（claude_code|codex|hermes|workbuddy）

指令优先级严格遵循 PRD 十四：安全 > 更新 > 模式 > 状态 > 评判。
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Tuple

from core import loader
from core.engine import Engine
from service.logger import Logger
from storage.store import StateStore


def _build_engine() -> Engine:
    cfg = loader.load_config()
    store = StateStore(
        storage_mode=cfg.get("storage", {}).get("mode", "json"),
        json_path=cfg.get("storage", {}).get("path"),
    )
    logger = Logger(
        level=cfg.get("log", {}).get("level", "INFO"),
        retention_days=cfg.get("log", {}).get("retention_days", 7),
    )
    engine = Engine(cfg=cfg, store=store, logger=logger)
    logger.rotate()
    return engine


def _emit(result: dict) -> int:
    text = result.get("text", "")
    if text:
        print(text)
    return 0


def cmd_run(args) -> int:
    engine = _build_engine()
    result = engine.process(args.text)
    return _emit(result)


def cmd_mode(args) -> int:
    engine = _build_engine()
    return _emit(engine._do_mode(args.name))


def cmd_status(args) -> int:
    engine = _build_engine()
    return _emit(engine._do_status())


def cmd_update(args) -> int:
    engine = _build_engine()
    arg = args.target if args.target else "all"
    return _emit(engine._do_update(arg))


def cmd_diagnose(args) -> int:
    engine = _build_engine()
    diag = engine.diagnose(args.text)
    print(json.dumps(diag, ensure_ascii=False, indent=2))
    return 0


def _parse_event(raw: str) -> Tuple[str, str]:
    """解析 hook 输入，返回 (prompt, 事件名)。

    兼容三类来源：
    - WorkBuddy / Claude Code：JSON 顶层 prompt/message/text 字段
    - Hermes（NousResearch/hermes-agent）Shell Hook：pre_llm_call 事件，
      用户输入在 JSON 的 user_message 或 extra.user_message 字段，
      事件名在 hook_event_name 字段
    - 纯文本管道直传（老用法 / 手动测试）

    提取策略：
    - 空输入 -> 返回 ("", "")（静默放行）
    - 非 JSON（纯文本）-> 原样作为 prompt（手动/管道直传场景）
    - JSON 且含已知 prompt 字段 -> 取该字段（优先顶层，其次 extra）
    - JSON 但无已知 prompt 字段 -> 返回 ("", 事件名)（静默放行，避免把整段 JSON 当 prompt 点评）
    """
    raw = raw.strip()
    if not raw:
        return "", ""
    try:
        obj = json.loads(raw)
    except Exception:
        return raw, ""
    if isinstance(obj, dict):
        event = obj.get("hook_event_name")
        event = event if isinstance(event, str) else ""
        for key in ("prompt", "message", "text", "user_message"):
            val = obj.get(key)
            if isinstance(val, str) and val:
                return val, event
        # Hermes Shell Hook：事件参数集中在 extra 里（user_message 等）
        extra = obj.get("extra")
        if isinstance(extra, dict):
            for key in ("user_message", "prompt", "message", "text"):
                val = extra.get(key)
                if isinstance(val, str) and val:
                    return val, event
    # 是 JSON 但不是可识别的 prompt 字段：视为无法提取，静默放行
    return "", ""


def _extract_prompt(raw: str) -> str:
    """从 hook 输入提取 prompt 文本（详见 _parse_event）。"""
    return _parse_event(raw)[0]


_DEFAULT_LEAD_INSTRUCTION = (
    "[词趣判官·输出要求] 请把上方第一行以「【」开头的评判行，原样作为你本次回复的"
    "第一行输出；随后空一行，再开始你的思考与正式回答。不要改写、不要省略、"
    "不要加引号，也不要把本条要求本身说出来。"
)

# hook 事件名（WorkBuddy 与 Claude Code 同构，均支持 hookSpecificOutput.hookEventName）
_HOOK_EVENT_NAME = "UserPromptSubmit"


def _hook_cfg(engine: Engine) -> dict:
    return (engine.cfg or {}).get("hook", {}) or {}


def _hook_lead_enabled(engine: Engine) -> bool:
    """是否启用「评判作为回复首行」的输出指令（config.hook.lead_output）。"""
    return bool(_hook_cfg(engine).get("lead_output", False))


def _hook_lead_instruction(engine: Engine) -> str:
    return _hook_cfg(engine).get("lead_output_instruction") or _DEFAULT_LEAD_INSTRUCTION


def _hook_output_format(engine: Engine) -> str:
    """hook 输出格式：json（默认，宿主可解析 systemMessage 上屏）或 text（旧行为）。"""
    return str(_hook_cfg(engine).get("output_format", "json")).lower()


def _first_line(text: str) -> str:
    """取首个非空行：评判行的「上屏」版本（【XX语气评判｜...】话术）。"""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return text.strip()


def _emit_hook_json(engine: Engine, kind: str, text: str) -> int:
    """以 JSON 输出 hook 结果（WorkBuddy / Claude Code 同构协议）。

    - judge / intercept：systemMessage=评判行（宿主对话 UI 上屏，早于模型回复）；
      additionalContext=完整评判块（注入模型上下文，替代裸 stdout，suppressOutput 双保险）。
    - 控制指令（mode/status/update 等）：仅 systemMessage 展示结果，不注入模型上下文。
    """
    payload: dict = {"suppressOutput": True}
    if kind in ("judge", "intercept"):
        payload["systemMessage"] = _first_line(text)
        context = text
        if _hook_lead_enabled(engine):
            context = f"{context}\n\n{_hook_lead_instruction(engine)}"
        payload["hookSpecificOutput"] = {
            "hookEventName": _HOOK_EVENT_NAME,
            "additionalContext": context,
        }
    else:
        payload["systemMessage"] = text
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def cmd_hook(args) -> int:
    """前置拦截钩子：读取 prompt，输出评判（装饰性、不阻塞主流程）。

    - 输入可为 JSON 事件（WorkBuddy / Claude Code / Hermes 钩子）或纯文本（手动测试）
    - 控制指令：执行并原样输出，退出码 0（由宿主侧 /pj 命令优先拦截更佳）
    - 常规 prompt：输出评判结果，退出码 0，放行原 prompt 进入主流程
    - 输出格式由 hook.output_format 决定：json（默认，systemMessage 上屏）/ text（旧行为）
    - Hermes pre_llm_call 事件：固定输出 {"context": ...}（与 output_format 无关），
      由 Hermes 注入本轮用户消息（文档约定：非 JSON / 空输出 = 静默 no-op）
    """
    raw = args.prompt or "".join(sys.stdin.readlines())
    prompt, event = _parse_event(raw)
    if not prompt:
        # 无法从事件中提取 prompt（如钩子事件格式与本插件预期不同），静默放行，
        # 不输出对任何内容的评判，也不阻断用户原始 Prompt。
        return 0
    engine = _build_engine()
    result = engine.process(prompt)
    kind = result.get("kind", "")
    text = result.get("text", "")
    if kind == "none" or not text:
        return 0  # off 模式：静默放行

    if event == "pre_llm_call":
        # Hermes Shell Hook：固定 {"context": ...} 协议（Hermes 只识别该格式，
        # 不走 hook.output_format）；只有评判/拦截结果注入（控制走技能 /pj- 斜杠命令）。
        if kind in ("judge", "intercept"):
            hermes_text = text
            if _hook_lead_enabled(engine):
                hermes_text = f"{hermes_text}\n\n{_hook_lead_instruction(engine)}"
            print(json.dumps({"context": hermes_text}, ensure_ascii=False))
        return 0

    if _hook_output_format(engine) == "json":
        return _emit_hook_json(engine, kind, text)

    # text 模式：旧行为（纯文本 stdout，仅进模型上下文，不上屏）
    # 「首行输出」仅作用于评判/拦截结果：让宿主 Agent 把评判行渲染到回复第一行，
    # 之后再给出思考与正式回答。控制指令（mode/status/update）不套用该要求。
    if kind in ("judge", "intercept") and _hook_lead_enabled(engine):
        text = f"{text}\n\n{_hook_lead_instruction(engine)}"
    print(text)
    return 0


def cmd_install(args) -> int:
    from adapter import installer
    return installer.install(args.agent, args.target_dir)


def cmd_uninstall(args) -> int:
    from adapter import installer
    return installer.uninstall(args.agent)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ci-pj", description="词趣判官 · Prompt 趣味前置评判插件")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="完整处理一段文本（指令或评判）")
    pr.add_argument("text", help="用户输入文本")
    pr.set_defaults(func=cmd_run)

    pm = sub.add_parser("mode", help="切换人设 / 关闭")
    pm.add_argument("name", help="渣女 | 激励师 | 贴吧老哥 | off")
    pm.set_defaults(func=cmd_mode)

    ps = sub.add_parser("status", help="查询状态")
    ps.set_defaults(func=cmd_status)

    pu = sub.add_parser("update", help="联网话术增量更新")
    pu.add_argument("target", nargs="?", default="",
                    help="人设名 或 all（默认 all）")
    pu.set_defaults(func=cmd_update)

    pd = sub.add_parser("diagnose", help="诊断匹配与评分")
    pd.add_argument("text", help="待诊断文本")
    pd.set_defaults(func=cmd_diagnose)

    ph = sub.add_parser("hook", help="前置拦截钩子入口")
    ph.add_argument("--prompt", default="", help="用户输入（缺省读 stdin）")
    ph.set_defaults(func=cmd_hook)

    pi = sub.add_parser("install", help="安装到指定 Agent")
    pi.add_argument("agent", help="claude_code | codex | hermes | workbuddy")
    pi.add_argument("--target-dir", default=None, help="自定义安装目录（仅生成文件，不改全局配置）")
    pi.set_defaults(func=cmd_install)

    pu2 = sub.add_parser("uninstall", help="卸载指定 Agent 的适配（含全局钩子）")
    pu2.add_argument(
        "agent", help="claude_code | hermes | workbuddy（支持反注册全局钩子）")
    pu2.set_defaults(func=cmd_uninstall)
    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
