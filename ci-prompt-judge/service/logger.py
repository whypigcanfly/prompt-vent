"""日志体系（PRD 十八）。

分类：运行日志 / 评分日志 / 话术日志 / 更新日志 / 异常日志
分级：INFO、WARN、ERROR、DEBUG
规范：每条带时间戳、场景、角色、唯一标识；支持自动轮转、过期清理。
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import core.pathutil as pathutil

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}


class Logger:
    def __init__(self, level: str = "INFO", retention_days: int = 7,
                 log_dir: Optional[str] = None):
        self.level = level
        self.retention_days = retention_days
        self.log_dir = Path(os.path.expanduser(
            log_dir or pathutil.default_log_dir()))
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _today_file(self) -> Path:
        return self.log_dir / f"ci-pj-{time.strftime('%Y-%m-%d')}.log"

    def log(self, level: str, category: str, message: str,
            persona: str = "", **meta: Any) -> None:
        if _LEVELS.get(level, 20) < _LEVELS.get(self.level, 20):
            return
        record = {
            "ts": self._now(),
            "level": level,
            "category": category,
            "persona": persona,
            "id": uuid.uuid4().hex[:8],
            "msg": message,
        }
        if meta:
            record["meta"] = meta
        try:
            with open(self._today_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 日志失败不阻断主流程

    def rotate(self) -> None:
        """清理超过保留天数的日志文件。"""
        try:
            cutoff = time.time() - self.retention_days * 86400
            for f in self.log_dir.glob("ci-pj-*.log"):
                m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
                if m and os.path.getmtime(f) < cutoff:
                    f.unlink(missing_ok=True)
        except Exception:
            pass

    # 便捷方法
    def info(self, category, message, **kw):
        self.log("INFO", category, message, **kw)

    def warn(self, category, message, **kw):
        self.log("WARN", category, message, **kw)

    def error(self, category, message, **kw):
        self.log("ERROR", category, message, **kw)

    def debug(self, category, message, **kw):
        self.log("DEBUG", category, message, **kw)
