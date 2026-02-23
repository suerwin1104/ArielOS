# -*- coding: utf-8 -*-
"""
modules/harness.py — ArielOS 安全與稽核模組

包含：Shield (防禦協議), Harness (L1/L5 框架), AuditLogger (稽核日誌)
"""

import re
import json
import shutil
import subprocess
import datetime
from pathlib import Path

from .config import log, BASE_DIR


class Shield:
    """L6: 防禦協議 2.0 (Security & Governance)"""
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.forbidden_patterns = [
            (r'(printenv|echo\s+\$|cat\s+\.env|process\.env)', "🚫 [Env Protection] 禁止讀取環境變數"),
            (r'(\.ssh|id_rsa|aws/credentials)', "🚨 [Canary Logic] 觸發誘捕：禁止存取敏感憑證"),
            (r'(echo\s+.*?>.*?|write|cp|mv).*?(AGENT\.md|SOUL\.md|SHIELD\.md)', "🔒 [Immutable Core] 禁止修改核心治理檔案"),
            (r'(train|fine-tune|nmap|ddos)', "⚠️ [Resource Pre-check] 高算力/高風險指令需二次確認"),
            (r'(cron\.add|cron\.schedule|cron\.create|schedule_job|add_cron)', "🚫 [Cron Shield] 禁止大腦直接呼叫排程工具，請改用 ArielOS Watcher (routines.json)")
        ]

    def scan(self, command):
        """掃描指令特徵碼"""
        cmd_lower = command.lower()
        for pattern, warning in self.forbidden_patterns:
            if re.search(pattern, cmd_lower):
                log(f"🛡️ Shield 攔截: {warning}")
                return False, warning
        return True, "Safe"


class Harness:
    """ArielOS L1-L6 Harness 驅動框架 (效能優化版)"""

    WRITE_KEYWORDS = [
        "修改", "編輯", "建立", "刪除", "新增", "重構", "寫入", "更新",
        "改", "加", "移除", "重命名", "create", "edit", "delete", "write",
        "refactor", "fix", "implement", "add", "remove", "rename", "code"
    ]

    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.checkpoint_dir = self.workspace / ".arielos" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def needs_checkpoint(self, query):
        """L1: 智慧判斷 - 只有寫入類指令才需要備份工作區"""
        q_lower = query.lower()
        return any(kw in q_lower for kw in self.WRITE_KEYWORDS)

    def create_checkpoint(self, task_id):
        """L1: 建立狀態檢查點 (僅程式碼目錄的輕量快照)"""
        log(f"🔄 L1 Checkpoint: 備份工作區 {task_id}")
        cp_path = self.checkpoint_dir / f"{task_id}_before"
        if cp_path.exists():
            shutil.rmtree(cp_path)
        shutil.copytree(self.workspace, cp_path, ignore=shutil.ignore_patterns(
            '.git', '.arielos', '__pycache__', 'node_modules', '*.log', '*.jsonl'
        ))
        return cp_path

    def rollback(self, task_id):
        """L1: 執行回滾"""
        log(f"⚠️ L1 Rollback: 任務 {task_id} 驗證失敗，恢復狀態")
        cp_path = self.checkpoint_dir / f"{task_id}_before"
        if cp_path.exists():
            for item in self.workspace.iterdir():
                if item.name not in ['.git', '.arielos']:
                    if item.is_dir():
                        try: shutil.rmtree(item)
                        except: pass
                    else:
                        try: item.unlink()
                        except: pass
            for item in cp_path.iterdir():
                if item.is_dir():
                    shutil.copytree(item, self.workspace / item.name)
                else:
                    shutil.copy2(item, self.workspace / item.name)
            return True
        return False

    def validate(self):
        """L5: 真相阻力驗證 (Phase 5: Execution-Conditioned Reasoning)"""
        log("🔍 L5 Validation: 執行自動化驗證與真相阻力測試...")
        for py_file in self.workspace.glob("**/*.py"):
            try:
                res_syntax = subprocess.run(
                    ['python', '-m', 'py_compile', str(py_file)],
                    check=False, capture_output=True, text=True
                )
                if res_syntax.returncode != 0:
                    error_msg = res_syntax.stderr.strip() or res_syntax.stdout.strip()
                    log(f"❌ 驗證失敗: {py_file.name} 語法錯誤")
                    return False, f"Syntax error in {py_file.name}:\n{error_msg}"

                res_exec = subprocess.run(
                    ['python', str(py_file)],
                    check=False, capture_output=True, text=True,
                    timeout=5, cwd=str(self.workspace)
                )
                if res_exec.returncode != 0:
                    error_msg = res_exec.stderr.strip() or res_exec.stdout.strip()
                    log(f"❌ 執行失敗: {py_file.name} 執行期錯誤 (Runtime Error)")
                    return False, f"Runtime error in {py_file.name} (Exit code {res_exec.returncode}):\n{error_msg}"

                log(f"✅ {py_file.name} 通過語法與執行測試。")
            except subprocess.TimeoutExpired:
                log(f"❌ 執行逾時: {py_file.name} 跑超過 5 秒被強制中斷")
                return False, f"Timeout error in {py_file.name}: 腳本執行超過 5 秒，可能存在無窮迴圈。"
            except Exception as e:
                return False, f"Validation execution error: {e}"
        return True, ""


class AuditLogger:
    """L3/L4: 磁碟即真相 - 稽核日誌管理"""
    def __init__(self, log_path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, task_id, query, result, success, agent_id="unknown"):
        """記錄執行足跡 (含代理人識別)"""
        timestamp = datetime.datetime.now().isoformat()
        entry = {
            "timestamp": timestamp,
            "task_id": task_id,
            "agent_id": agent_id,
            "query": query,
            "success": success,
            "result_summary": result[:200] + "..." if len(result) > 200 else result
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
