# -*- coding: utf-8 -*-
"""
modules/config.py — ArielOS 集中配置模組

所有常數、路徑、模型名稱均在此定義。
更換模型或調整路徑只需修改此單一檔案。
"""

import requests
import datetime
import time
from pathlib import Path

# ── 路徑配置 ─────────────────────────────────────────────────────────────────
BASE_DIR = Path.home() / "Ariel_System"
CACHE_PATH = BASE_DIR / "Shared_Vault" / "cache_buffer.json"
CACHE_PATH.parent.mkdir(exist_ok=True, parents=True)
KANBAN_DB_PATH = BASE_DIR / "Shared_Vault" / "kanban.json"
AGENTS_CONFIG_PATH = BASE_DIR / "Shared_Vault" / "agents.json"
ROUTINES_PATH = BASE_DIR / "Shared_Vault" / "routines.json"
DATA_SANDBOX_PATH = BASE_DIR / "Shared_Vault" / "data_sandbox"
DATA_SANDBOX_PATH.mkdir(exist_ok=True, parents=True)

# ── Ollama API ────────────────────────────────────────────────────────────────
OLLAMA_API = "http://127.0.0.1:11434/api/generate"

# ── 模型配置 (集中管理，更換模型只需改此處) ──────────────────────────────────
# 小腦：使用 instruction-tuned + q4_K_M 量化版，速度比預設版快 ~30%
# 💡 請先執行 ollama pull gemma3:4b-it-q4_K_M 後再使用量化版
CEREBELLUM_MODEL = "gemma3:4b-it-q4_K_M"

# 🚀 意圖分類專用模型 (FastTrack)：建議使用 1.5B 等級模型以達成秒回
# 若電腦配備較佳，可設為與 CEREBELLUM_MODEL 相同
# INTENT_MODEL = "gemma3:4b-it-q4_K_M" 
INTENT_MODEL = "qwen2.5:1.5b-instruct-q8_0" # 若要極速，請取消此行註解並執行 ollama pull

# 備用模型：若量化版未安裝或 Ollama 超時，系統自動降級至此模型繼續服務
CEREBELLUM_FALLBACK_MODEL = "gemma3:4b"
# Dispatcher 角色扮演任務也用小腦模型即可
DISPATCHER_MODEL = "gemma3:4b-it-q4_K_M"

# ── 閒置門檻 ─────────────────────────────────────────────────────────────────
IDLE_THRESHOLD = 1800  # 秒：30 分鐘無活動則觸發好奇心

# ── 工具函式 ─────────────────────────────────────────────────────────────────
def ollama_post(url, json, timeout=120):
    """Thread-safe Ollama post."""
    return requests.post(url, json=json, timeout=timeout)


def log(msg):
    t = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{t}] 🏰 [總部] {msg}")
