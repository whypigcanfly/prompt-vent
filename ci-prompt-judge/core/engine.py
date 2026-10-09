"""核心控制层 / 引擎（PRD 二、十二、十四、十五、十七、十九）。

职责：状态管理、指令调度、流程管控、优先级处理。
全局指令优先级（PRD 十四，自上而下递减）：
  1. 安全拦截（违规直接拦截，终止后续）
  2. 话术更新指令 /pj-update-all、/pj-update
  3. 模式控制指令 /pj-mode
  4. 状态查询指令 /pj-status
  5. 常规 Prompt 评判流程
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core import loader
from core.formatter import format_output, should_output
from core.rules_matcher import (describe_matches, detect_whitelist, match_rules,
                                top_rule)
from core.scoring import compute_score, describe_dimensions
from core.speech_renderer import render
from service import update as update_svc
from storage.store import StateStore


class Engine:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None,
                 store: Optional[StateStore] = None, logger=None):
        self.cfg = cfg or loader.load_config()
        self.rules = loader.load_rules()
        self.personas = loader.load_personas()
        self.store = store or StateStore(
            storage_mode=self.cfg.get("storage", {}).get("mode", "json"),
            json_path=self.cfg.get("storage", {}).get("path"),
        )
        self.logger = logger
        self.prefix = self.cfg.get("command_prefix", "/pj-")
        self.valid_modes = self.cfg.get("modes", ["渣女", "激励师", "贴吧老哥", "off"])

    # ---------- 指令识别（PRD 四、十四）----------
    def parse_command(self, text: str) -> Optional[Tuple[str, str]]:
        """返回 (cmd_type, arg) 或 None。cmd_type ∈ mode|status|update。"""
        t = text.strip()
        if not t.startswith(self.prefix):
            return None
        body = t[len(self.prefix):].strip()
        if body.startswith("mode"):
            return ("mode", body[len("mode"):].strip())
        if body == "status":
            return ("status", "")
        if body.startswith("update"):
            return ("update", body[len("update"):].strip())
        return ("unknown", body)

    # ---------- 安全拦截（优先级最高）----------
    def _safety_blocked(self, prompt: str) -> bool:
        safety = self.cfg.get("safety", {})
        if not safety.get("enabled", False):
            return False
        blocklist = safety.get("blocklist", [])
        return any(w in prompt for w in blocklist)

    # ---------- 主入口 ----------
    def process(self, text: str) -> Dict[str, Any]:
        cmd = self.parse_command(text)
        if cmd is not None:
            ctype, arg = cmd
            if ctype == "update":
                return self._do_update(arg)
            if ctype == "mode":
                return self._do_mode(arg)
            if ctype == "status":
                return self._do_status()
            return {"kind": "unknown_command", "text": f"未知指令：{text}"}

        # 常规 Prompt：先安全拦截
        if self._safety_blocked(text):
            msg = "【安全拦截】内容触发安全规则，已拦截，未执行趣味评判。"
            if self.logger:
                self.logger.warn("safety", "触发安全拦截", prompt=text[:30])
            return {"kind": "intercept", "text": msg}

        return self._do_judge(text)

    # ---------- 评判流程（PRD 二、五）----------
    def _do_judge(self, prompt: str) -> Dict[str, Any]:
        mode = self.store.get_mode()
        if not should_output(mode):
            # off 模式：无任何输出，直接进入原对话逻辑
            return {"kind": "none", "text": ""}

        matched = match_rules(prompt, self.rules)
        # 白名单命中：关键词/正则命中，或命中了标记为 whitelist 的专业规则（如 R04 代码）
        whitelist_hit = detect_whitelist(prompt, self.rules) or any(
            r.get("whitelist") for r in matched)
        is_short = any(r.get("id") == "R01" for r in matched) or len(prompt.strip()) <= 15
        score_info = compute_score(prompt, self.rules, self.cfg, whitelist_hit, is_short)
        comment = render(mode, matched, self.personas)
        output = format_output(mode, score_info["score"], comment, prompt)

        if self.logger:
            self.logger.info(
                "score",
                f"得分{score_info['score']} 命中{describe_matches(matched)}",
                persona=mode,
                score=score_info["score"],
                rules=describe_matches(matched),
            )
        return {
            "kind": "judge",
            "text": output,
            "mode": mode,
            "score": score_info["score"],
            "matched": [r.get("id") for r in matched],
            "dimensions": score_info["dimensions"],
        }

    # ---------- 模式控制（PRD 四）----------
    def _do_mode(self, arg: str) -> Dict[str, Any]:
        if arg == "off" or arg in ("关闭",):
            self.store.set_mode("off")
            return {"kind": "mode", "text": "词趣判官已关闭，后续不再评判与打分。"}
        if arg in ("渣女", "激励师", "贴吧老哥"):
            self.store.set_mode(arg)
            if self.logger:
                self.logger.info("runtime", f"切换模式->{arg}", persona=arg)
            return {"kind": "mode", "text": f"词趣判官已切换为「{arg}」语气。"}
        return {
            "kind": "mode_help",
            "text": "用法：/pj-mode 渣女 | 激励师 | 贴吧老哥 | off",
        }

    # ---------- 状态查询（PRD 四）----------
    def _do_status(self) -> Dict[str, Any]:
        mode = self.store.get_mode()
        persona_count = len(self.personas.get("personas", {}))
        rule_count = len([r for r in self.rules.get("feature_rules", [])
                          if r.get("status", "enabled") == "enabled"])
        text = (
            f"词趣判官状态：\n"
            f"· 当前模式：{mode}\n"
            f"· 内置人设：{persona_count} 个（渣女 / 激励师 / 贴吧老哥）\n"
            f"· 启用规则：{rule_count} 条\n"
            f"· 存储模式：{self.cfg.get('storage', {}).get('mode')}\n"
            f"· 指令：/pj-mode <人设|off> · /pj-status · /pj-update <人设> · /pj-update-all"
        )
        return {"kind": "status", "text": text, "mode": mode}

    # ---------- 话术更新（PRD 11.7）----------
    def _do_update(self, arg: str) -> Dict[str, Any]:
        if arg == "all" or arg == "":
            roles = list(self.personas.get("personas", {}).keys())
            reports = [update_svc.update_persona(r, cfg=self.cfg, store=self.store,
                                                 logger=self.logger) for r in roles]
            lines = [f"【{r.get('persona', r)}】+{r.get('added',0)} 条（共 {r.get('total',0)}）"
                     for r in reports if isinstance(r, dict)]
            text = "话术增量更新完成：\n" + "\n".join(lines) if reports else "无更新。"
            return {"kind": "update", "text": text, "reports": reports}
        if arg in self.personas.get("personas", {}):
            rep = update_svc.update_persona(arg, cfg=self.cfg, store=self.store,
                                            logger=self.logger)
            if not rep.get("ok"):
                text = f"更新未完成：{rep.get('reason')}"
                if rep.get("suggestions"):
                    text += "\n检索建议词：" + " / ".join(rep["suggestions"])
            else:
                text = f"角色「{arg}」更新完成：新增 {rep['added']} 条，现存 {rep['total']} 条。"
            return {"kind": "update", "text": text, "report": rep}
        return {"kind": "update_help", "text": "用法：/pj-update <渣女|激励师|贴吧老哥> | /pj-update-all"}

    # ---------- 便捷诊断 ----------
    def diagnose(self, prompt: str) -> Dict[str, Any]:
        """不输出评判，仅返回匹配/评分分析，便于调试与演示。"""
        matched = match_rules(prompt, self.rules)
        # 白名单命中：关键词/正则命中，或命中了标记为 whitelist 的专业规则（如 R04 代码）
        whitelist_hit = detect_whitelist(prompt, self.rules) or any(
            r.get("whitelist") for r in matched)
        is_short = any(r.get("id") == "R01" for r in matched) or len(prompt.strip()) <= 15
        score_info = compute_score(prompt, self.rules, self.cfg, whitelist_hit, is_short)
        top = top_rule(matched)
        return {
            "prompt": prompt,
            "matched_rules": describe_matches(matched),
            "top_rule": top.get("id") if top else None,
            "whitelist_hit": whitelist_hit,
            "score": score_info["score"],
            "dimensions": score_info["dimensions"],
            "short_penalized": score_info["short_penalized"],
        }
