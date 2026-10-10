"""适配层基类（PRD 十一、十二.1 接入适配层）。

统一接入模板：新增任意 Agent 仅需录入平台标识、输入格式、兼容规则即可完成适配。
各 Agent 适配器职责：
- 生成该平台可识别的命令文件（slash command）
- 生成前置拦截钩子配置片段（best-effort，附人工校验提示）
- 输出安装说明

基类提供默认实现；子类按需覆盖 generate / install_dir / 命令内容即可。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple


class AgentAdapter:
    name = "abstract"
    # 该 Agent 是否支持以 markdown 命令文件注册 slash 命令
    supports_command_file = True

    # ---------- 可被覆盖的默认实现 ----------
    def command_filename(self) -> str:
        return "pj.md"

    def command_content(self) -> str:
        return (
            "---\n"
            "description: 词趣判官 - Prompt 趣味前置评判\n"
            "---\n"
            '!ci-pj run "$ARGUMENTS"\n'
        )

    def hook_instructions(self) -> str:
        return (
            f"[{self.name}] 安装说明：\n"
            "1) 安装 ci-pj：pip install -e .\n"
            "2) 命令文件已生成，请移动到该 Agent 的命令目录\n"
            "3) 前置拦截：注册钩子运行 `ci-pj hook`（读取 prompt）\n"
        )

    def install_dir(self, target: str | None) -> Path:
        if target:
            return Path(target) / self.name
        return Path.cwd() / ".ci-pj-adapt" / self.name

    def hook_driver_path(self, target: str | None = None) -> Path:
        """全局钩子驱动脚本路径（installer 卸载反注册时使用）。"""
        return self.install_dir(target) / "hook_driver.sh"

    def uninstall_files(self) -> List[str]:
        """卸载时删除本插件生成的文件/目录。

        默认整目录删除 install_dir(None)（该目录为本插件专有时安全）；
        目录与宿主其他文件共用时（如 Claude Code 的 ~/.claude/commands），
        子类必须覆盖为精确删除，避免误删用户自有文件。
        """
        import shutil

        d = self.install_dir(None)
        if d.exists():
            shutil.rmtree(d)
            return [str(d)]
        return []

    # ---------- 默认生成流程（子类可整体覆盖）----------
    def generate(self, target: str | None = None) -> Tuple[List[str], str]:
        d = self.install_dir(target)
        d.mkdir(parents=True, exist_ok=True)
        created: List[str] = []
        if self.supports_command_file:
            cf = d / self.command_filename()
            cf.write_text(self.command_content(), encoding="utf-8")
            created.append(str(cf))
        notes = self.hook_instructions()
        return created, notes

    @staticmethod
    def write_json(path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
