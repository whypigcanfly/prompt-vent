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
from typing import Optional

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


def cmd_hook(args) -> int:
    """前置拦截钩子：读取 prompt，输出评判（装饰性、不阻塞主流程）。

    - 控制指令：执行并原样输出，退出码 0（由宿主侧 /pj 命令优先拦截更佳）
    - 常规 prompt：输出评判结果，退出码 0，放行原 prompt 进入主流程
    """
    prompt = args.prompt or "".join(sys.stdin.readlines())
    engine = _build_engine()
    result = engine.process(prompt)
    text = result.get("text", "")
    if result.get("kind") == "none":
        return 0  # off 模式：静默放行
    if text:
        # 评判/指令结果输出到 stdout，宿主可显示为系统提示
        print(text)
    return 0


def cmd_install(args) -> int:
    from adapter import installer
    return installer.install(args.agent, args.target_dir)


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
    pi.add_argument("--target-dir", default=None, help="自定义安装目录")
    pi.set_defaults(func=cmd_install)
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
