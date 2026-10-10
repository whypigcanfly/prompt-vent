# -*- coding: utf-8 -*-
"""hook 输出单测（issue #2：评判结果上屏）。

验证 `ci-pj hook` 的 JSON 输出协议（WorkBuddy / Claude Code 同构）：
- judge：systemMessage=评判行（上屏）+ hookSpecificOutput.additionalContext（模型上下文）
- 控制指令：仅 systemMessage，不注入上下文
- off / 空 prompt：静默放行
- text 回退模式：旧行为
- claude_code 适配器：钩子幂等注册/卸载

运行：cd ci-prompt-judge && python -m unittest discover -s tests -v
（零第三方依赖，stdlib unittest）
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
from core.engine import Engine
from storage.store import StateStore

REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_engine(tmp: tempfile.TemporaryDirectory, cfg_overrides: dict | None = None) -> Engine:
    """构造无副作用的 Engine：内存存储 + 指向仓库内置资源的配置。"""
    cfg = json.loads(
        (REPO_ROOT / "core" / "data" / "config" / "config.default.json").read_text("utf-8")
    )
    # 资源路径指向仓库内置数据（loader 默认按包路径读取，这里保持默认即可）
    if cfg_overrides:
        for k, v in cfg_overrides.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    store = StateStore(storage_mode="memory")
    store.set_mode(cfg.get("default_mode", "渣女"))
    return Engine(cfg=cfg, store=store, logger=None)


def _run_hook(engine: Engine, prompt: str) -> tuple[int, str]:
    """以给定 engine 执行 cmd_hook，捕获 stdout。返回 (exit_code, stdout)。"""
    buf = io.StringIO()
    with mock.patch.object(main, "_build_engine", return_value=engine):
        with contextlib.redirect_stdout(buf):
            args = type("Args", (), {"prompt": prompt})()
            code = main.cmd_hook(args)
    return code, buf.getvalue()


class TestHookJsonOutput(unittest.TestCase):
    """JSON 模式（默认）：评判行上屏 + additionalContext 注入。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = _make_engine(self.tmp)
        self.engine.store.set_mode("渣女")

    def tearDown(self):
        self.tmp.cleanup()

    def test_judge_json_structure(self):
        code, out = _run_hook(self.engine, "帮我写一个电商首页")
        self.assertEqual(code, 0)
        payload = json.loads(out.strip())
        # systemMessage = 评判行（首行，以「【」开头）
        self.assertTrue(payload["systemMessage"].startswith("【"))
        self.assertIn("提示词完整性得分", payload["systemMessage"])
        self.assertEqual(payload["systemMessage"], payload["systemMessage"].strip())
        # additionalContext = 完整评判块（含放行提示词与 lead 指令）
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("---放行提示词---", ctx)
        self.assertIn("帮我写一个电商首页", ctx)
        self.assertIn("[词趣判官·输出要求]", ctx)
        self.assertIn("【", ctx.splitlines()[0])
        # 协议字段
        self.assertTrue(payload["suppressOutput"])
        self.assertEqual(
            payload["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
        )

    def test_system_message_is_first_line_only(self):
        _, out = _run_hook(self.engine, "帮我写一个电商首页")
        payload = json.loads(out.strip())
        # 评判行不含放行提示词块（多行内容只进 additionalContext）
        self.assertNotIn("---放行提示词---", payload["systemMessage"])

    def test_control_command_system_message_only(self):
        _, out = _run_hook(self.engine, "/pj-mode 激励师")
        payload = json.loads(out.strip())
        self.assertIn("systemMessage", payload)
        self.assertNotIn("hookSpecificOutput", payload)
        self.assertNotIn("additionalContext", payload)
        self.assertTrue(payload["suppressOutput"])
        # 控制指令已生效
        self.assertEqual(self.engine.store.get_mode(), "激励师")

    def test_status_command(self):
        _, out = _run_hook(self.engine, "/pj-status")
        payload = json.loads(out.strip())
        self.assertIn("渣女", payload["systemMessage"])
        self.assertNotIn("hookSpecificOutput", payload)

    def test_off_mode_silent(self):
        self.engine.store.set_mode("off")
        code, out = _run_hook(self.engine, "帮我写一个电商首页")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_empty_prompt_silent(self):
        code, out = _run_hook(self.engine, "")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_json_event_input(self):
        """stdin 传入宿主 JSON 事件（WorkBuddy/Claude Code 同构格式）。"""
        event = json.dumps({"prompt": "帮我写一个电商首页"}, ensure_ascii=False)
        code, out = _run_hook(self.engine, event)
        self.assertEqual(code, 0)
        payload = json.loads(out.strip())
        self.assertTrue(payload["systemMessage"].startswith("【"))


class TestHookTextFallback(unittest.TestCase):
    """text 回退模式：保持旧行为（纯文本 stdout）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = _make_engine(
            self.tmp, {"hook": {"output_format": "text"}}
        )
        self.engine.store.set_mode("渣女")

    def tearDown(self):
        self.tmp.cleanup()

    def test_text_mode_plain_output(self):
        code, out = _run_hook(self.engine, "帮我写一个电商首页")
        self.assertEqual(code, 0)
        text = out.strip()
        # 非 JSON：第一行是评判行，含放行提示词块与 lead 指令
        self.assertTrue(text.splitlines()[0].startswith("【"))
        self.assertIn("---放行提示词---", text)
        self.assertIn("[词趣判官·输出要求]", text)


class TestClaudeCodeHookRegister(unittest.TestCase):
    """claude_code 适配器：用户级全局钩子幂等注册/卸载（隔离 HOME）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        import adapter.claude_code as cc

        self.cc = cc
        # 隔离：Path.home() 与 GLOBAL_SETTINGS 都指向临时目录
        self._patchers = [
            mock.patch.object(Path, "home", return_value=self.root),
            mock.patch.object(cc, "GLOBAL_SETTINGS", self.root / ".claude" / "settings.json"),
        ]
        for p in self._patchers:
            p.start()
        self.adapter = cc.ClaudeCodeAdapter()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        self.tmp.cleanup()

    def _gen(self):
        return self.adapter.generate(None)

    def test_generate_default_registers_global_hook(self):
        created, _ = self._gen()
        # 4 命令文件 + 1 钩子驱动，均写入用户级目录
        self.assertEqual(len(created), 5)
        self.assertTrue((self.root / ".claude" / "commands" / "pj-mode.md").exists())
        self.assertTrue((self.root / ".claude" / "ci-pj" / "hook_driver.sh").exists())
        data = json.loads((self.root / ".claude" / "settings.json").read_text("utf-8"))
        groups = data["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0]["hooks"][0]["command"].endswith("hook_driver.sh"))

    def test_generate_with_target_no_global_change(self):
        target = self.root / "pkg"
        created, _ = self.adapter.generate(str(target))
        self.assertEqual(len(created), 5)
        # --target-dir 模式不写全局 settings.json
        self.assertFalse((self.root / ".claude" / "settings.json").exists())

    def test_register_idempotent_with_backup(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}),
            encoding="utf-8",
        )
        driver = self.root / ".claude" / "ci-pj" / "hook_driver.sh"
        self.adapter.register_global_hook(driver)
        self.adapter.register_global_hook(driver)  # 幂等
        data = json.loads(settings.read_text("utf-8"))
        groups = data["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(groups), 1)  # 去重：不重复注册
        self.assertEqual(groups[0]["hooks"][0]["command"], str(driver))
        self.assertIn("Stop", data["hooks"])  # 原有钩子保留
        self.assertTrue(list(settings.parent.glob("settings.json.ci-pj-bak-*")))

    def test_unregister_removes_only_own_hook(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{}", encoding="utf-8")
        driver = self.root / ".claude" / "ci-pj" / "hook_driver.sh"
        self.adapter.register_global_hook(driver)
        note = self.adapter.unregister_global_hook(driver)
        self.assertIn("已移除", note)
        data = json.loads(settings.read_text("utf-8"))
        self.assertNotIn("UserPromptSubmit", data.get("hooks", {}))

    def test_uninstall_files_keeps_foreign_commands(self):
        _, _ = self._gen()
        foreign = self.root / ".claude" / "commands" / "other-cmd.md"
        foreign.write_text("x", encoding="utf-8")
        removed = self.adapter.uninstall_files()
        self.assertFalse((self.root / ".claude" / "commands" / "pj-mode.md").exists())
        self.assertTrue(foreign.exists())  # 用户其他命令不受影响
        self.assertFalse((self.root / ".claude" / "ci-pj" / "hook_driver.sh").exists())
        self.assertTrue(any("hook_driver.sh" in f for f in removed))


if __name__ == "__main__":
    unittest.main()
