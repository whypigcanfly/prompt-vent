"""持久化存储层：本地 JSON 文件模式（默认正式）/ 内存模式（临时测试）。

PRD 十三：插件支持多层级持久化存储，解决重启、切换 Agent、重载后状态丢失问题。
- 内存模式（默认临时）：重启失效，适合临时测试
- 本地文件模式（默认正式）：JSON 配置文件，轻量化、易编辑、可备份
- 轻量数据库模式（扩展）：支持 SQLite（本文件预留接口）
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from core import pathutil


class StateStore:
    """当前运行模式与轻量状态的持久化。

    设计原则：无侵入、实时落盘、可备份导入导出。原生预制话术永久固化，
    不在此处覆盖；此处仅存运行态（mode）与用户增量（用户话术覆盖等）。
    """

    def __init__(self, storage_mode: str = "json", json_path: Optional[str] = None):
        self.mode = storage_mode  # "json" | "memory"
        self._lock = threading.RLock()
        self._mem: Dict[str, Any] = {}
        if json_path:
            self.json_path = Path(os.path.expanduser(json_path))
        else:
            self.json_path = Path(os.path.expanduser(pathutil.default_state_path()))
        self._ensure_file()

    # ---------- 文件保障 ----------
    def _ensure_file(self) -> None:
        if self.mode == "memory":
            return
        try:
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.json_path.exists():
                self._write({})
        except Exception:
            # 文件不可写时静默降级为内存模式，保证插件不崩溃
            self.mode = "memory"

    def _read(self) -> Dict[str, Any]:
        if self.mode == "memory":
            return self._mem
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data: Dict[str, Any]) -> None:
        if self.mode == "memory":
            self._mem = data
            return
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------- 运行态 API ----------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._read().get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            data = self._read()
            data[key] = value
            self._write(data)

    def get_mode(self) -> str:
        return self.get("mode") or "off"

    def set_mode(self, mode: str) -> None:
        self.set("mode", mode)

    def reset(self, default_mode: str = "激励师") -> None:
        """一键恢复默认运行态（PRD 12.2 重置）。话术库重置由各层分别处理。"""
        with self._lock:
            self._write({"mode": default_mode})

    # ---------- 备份 / 导入（PRD 13.3）----------
    def export_backup(self, target: str) -> str:
        src = self._read()
        Path(os.path.expanduser(target)).parent.mkdir(parents=True, exist_ok=True)
        with open(os.path.expanduser(target), "w", encoding="utf-8") as f:
            json.dump(src, f, ensure_ascii=False, indent=2)
        return target

    def import_backup(self, source: str) -> None:
        with open(os.path.expanduser(source), "r", encoding="utf-8") as f:
            data = json.load(f)
        self._write(data)
