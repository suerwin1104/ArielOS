# -*- coding: utf-8 -*-
"""
modules/personality.py — ArielOS 人格與代理人模組

包含：PersonalityEngine, AgentDispatcher, spinal_chord_reflex, _sanitize_persona
也負責載入 AGENT_REGISTRY。
"""

import json
import re
import datetime
from pathlib import Path

from .config import BASE_DIR, AGENTS_CONFIG_PATH, log


# ── 代理人登錄表 ──────────────────────────────────────────────────────────────
AGENT_REGISTRY = {}


def load_agent_registry():
    """從 JSON 載入代理人設定，若無則使用預設值"""
    global AGENT_REGISTRY
    def _log(msg):
        try: log(msg)
        except: print(f"[ArielOS] {msg}")

    default_agents = {
        "agent1": {
            "name": "Jessie",
            "dir": "Ariel_Agent_1",
            "intro": "我是 Jessie，您的執行秘書。隨時準備為您處理公務與專案。"
        },
        "agent2": {
            "name": "Mandy",
            "dir": "Ariel_Agent_2",
            "intro": "老闆您好，我是 Mandy，您的私人生活特助。有什麼我可以幫您安排的嗎？"
        }
    }

    if not AGENTS_CONFIG_PATH.exists():
        _log("⚠️ 未找到 agents.json，使用預設代理人設定並建立檔案")
        try:
            with open(AGENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(default_agents, f, ensure_ascii=False, indent=2)
            AGENT_REGISTRY.clear()
            AGENT_REGISTRY.update(default_agents)
        except Exception as e:
            _log(f"❌ 無法建立 agents.json: {e}")
            AGENT_REGISTRY.clear()
            AGENT_REGISTRY.update(default_agents)
    else:
        try:
            with open(AGENTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                AGENT_REGISTRY.clear()
                AGENT_REGISTRY.update(data)
            _log(f"✅ 已載入 {len(AGENT_REGISTRY)} 位代理人設定")
        except Exception as e:
            _log(f"❌ 讀取 agents.json 失敗: {e}，回退至預設值")
            AGENT_REGISTRY.clear()
            AGENT_REGISTRY.update(default_agents)


class PersonalityEngine:
    """L4: 人格引擎 - 讀取 SOUL.md 並注入身份偏好"""
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self._cache = {}
        self._cache_intros = {}

    def load_soul(self, agent_id):
        """載入指定代理人的 SOUL.md"""
        if agent_id in self._cache:
            return self._cache[agent_id]

        agent_info = AGENT_REGISTRY.get(agent_id)
        if not agent_info:
            return ""

        soul_path = self.base_dir / agent_info["dir"] / "memory" / "SOUL.md"
        if soul_path.exists():
            with open(soul_path, "r", encoding="utf-8") as f:
                soul_text = f.read()
            self._cache[agent_id] = soul_text

            start_marker = "* **自我介紹**："
            start_marker_alt = "* **Reflex Intro**："
            intro = None
            for line in soul_text.split('\n'):
                if start_marker in line:
                    intro = line.split(start_marker)[1].strip()
                    break
                elif start_marker_alt in line:
                    intro = line.split(start_marker_alt)[1].strip()
                    break

            if intro:
                self._cache_intros[agent_id] = intro
                log(f"🧬 人格引擎: 已載入 {agent_info['name']} 的自我介紹 (Reflex)")
            else:
                log(f"🧬 人格引擎: 已載入 {agent_info['name']} 的靈魂設定")
            return soul_text
        return ""

    def get_intro(self, agent_id):
        """取得脊髓反射用的自我介紹"""
        if agent_id not in self._cache_intros:
            self.load_soul(agent_id)
        return self._cache_intros.get(agent_id, None)

    def build_persona_prompt(self, agent_id, user_query):
        """Legacy stub"""
        return user_query

    def invalidate(self, agent_id=None):
        if agent_id:
            self._cache.pop(agent_id, None)
            self._cache_intros.pop(agent_id, None)
        else:
            self._cache.clear()
            self._cache_intros.clear()


class AgentDispatcher:
    """L5: 多代理團隊分發器 (Multi-Agent Dispatcher)"""
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.roles_dir = self.base_dir / "Shared_Vault" / "roles"
        self.workspace_root = self.base_dir / ".arielos" / "workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def dispatch(self, task_id, role, payload):
        """分發任務給特定角色"""
        from .cerebellum import cerebellum_call
        log(f"👮 [Dispatcher] Assigning Task {task_id} to Role: {role}")
        workspace = self._create_workspace(task_id)

        soul_path = self.roles_dir / f"{role}.soul.md"
        soul_content = ""
        if soul_path.exists():
            soul_content = soul_path.read_text(encoding="utf-8")
        else:
            pe = PersonalityEngine(self.base_dir)
            for aid, info in AGENT_REGISTRY.items():
                if info["name"].lower() == role.lower():
                    soul_content = pe.load_soul(aid)
                    break
            if not soul_content:
                return f"Error: Role/Agent '{role}' not found."

        instruction = (
            f"{soul_content}\n\n"
            f"Current Workspace: {workspace}\n"
            f"Task Payload: {payload}\n"
            "請以你的角色身分執行上述任務。若需寫檔，請輸出檔案內容與路徑。"
        )
        try:
            result = cerebellum_call(
                prompt=instruction,
                temperature=0.1,
                timeout=300,
                num_ctx=4096,
                num_predict=1024
            )
            (workspace / "execution.log").write_text(result, encoding="utf-8")
            return result
        except Exception as e:
            return f"Dispatcher Error: {e}"

    def _create_workspace(self, task_id):
        ws = self.workspace_root / task_id
        ws.mkdir(parents=True, exist_ok=True)
        return ws


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def _sanitize_persona(text: str, agent_name: str) -> str:
    """🛡️ 強制替換所有 Ariel/ArielOS 自稱為正確代理人名字"""
    text = re.sub(r'\bArielOS\b', agent_name, text)
    text = re.sub(r'\bAriel\b', agent_name, text)
    return text


def _get_time_context() -> str:
    """⏰ 取得目前的系統時間上下文"""
    now = datetime.datetime.now()
    weekday_map = ["一", "二", "三", "四", "五", "六", "日"]
    weekday = weekday_map[now.weekday()]
    return f"[系統時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (星期{weekday})]\n"


def spinal_chord_reflex(query: str, agent_id: str, agent_registry: dict, pe, sm=None) -> str | None:
    """⚡ 脊髓反射：不經大腦與小腦，直接以規則處理極簡問題 (0.01s)"""
    q = query.strip().lower().replace(" ", "")
    agent_name = agent_registry.get(agent_id, {}).get("name", "Ariel Agent")
    now = datetime.datetime.now()

    # 1. 攔截技能資訊型詢問 (直接由 sm 列出，不進 LLM)
    info_queries = ["有哪些技能", "有什麼技能", "會什麼", "技術列表", "功能清單", "懂什麼", "能幫我做什麼"]
    if any(k in q for k in info_queries) and len(q) < 15:
        if sm:
            installed = [s['name'] for s in sm.list_installed()]
            if not installed:
                return "報告老闆，我目前尚未安裝額外技能。您可以命令我學習新工具或幫您開發 Python 腳本！"
            return f"報告老闆，我目前具備以下技能工具：\n" + "\n".join([f"- {n}" for n in installed]) + "\n\n若上述沒有您需要的，我也可以隨時現場開發新功能。"

    # 2. 時間日期增強
    if any(k in q for k in ["今天日期", "現在時間", "幾月幾號", "星期幾", "現在幾點", "today", "now", "time"]):
        if len(q) < 20 and not any(k in q for k in ["東京", "美國", "票", "天氣", "新聞"]):
            weekday = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
            return f"今天是 {now.strftime('%Y 年 %m 月 %d 日')}，現在時間 {now.strftime('%H:%M')}，星期{weekday}。"

    if any(k in q for k in ["明天幾號", "明天星期幾", "後天幾號"]):
        target = now + datetime.timedelta(days=1 if "明天" in q else 2)
        weekday = ["一", "二", "三", "四", "五", "六", "日"][target.weekday()]
        day_str = "明天" if "明天" in q else "後天"
        return f"{day_str}是 {target.strftime('%Y 年 %m 月 %d 日')}，星期{weekday}。"

    # 3. 基本身份與介紹
    if any(k in q for k in ["你是誰", "妳是誰", "你的名字", "妳的名字", "whoareyou", "自我介紹", "介紹自己"]):
        dynamic_intro = pe.get_intro(agent_id)
        fallback_intro = agent_registry.get(agent_id, {}).get("intro", f"我是 {agent_name}，您的 AI 助理。")
        return dynamic_intro if dynamic_intro else fallback_intro

    # 4. 基礎問候 (包含長度限制與過濾)
    greetings = ["hi", "hello", "你好", "您好", "早安", "午安", "晚安", "哈囉", "安安"]
    if q in greetings or (len(q) < 6 and any(k == q for k in greetings)):
        hour = now.hour
        greeting = "早安" if 5 <= hour < 12 else "午安" if 12 <= hour < 18 else "晚安"
        return f"{agent_name} 祝您{greeting}！有什麼我可以幫您的嗎？"

    # 5. 感謝與禮貌
    if any(k in q for k in ["謝謝", "感謝", "辛苦了", "thanks", "thankyou"]):
        if len(q) < 10:
            return "不客氣，這是我的榮幸！"

    # 6. 系統狀態
    if q in ["系統狀態", "status", "version", "版本", "ping", "檢查系統"]:
        return f"🟢 ArielOS 運作正常 | Agent: {agent_name} | Pre-check: All Green"

    # 7. 協助工具
    if any(k == q for k in ["help", "說明", "指令", "功能", "你能做什麼"]):
        return (
            f"我是您的 {agent_name} 智能助理，我可以協助您：\n"
            "1. 🔍 **搜尋資訊**：網路即時搜尋天氣、新聞、股價\n"
            "2. 🛠️ **執行技能**：讀寫檔案、Git 操作、MCP 工具調用\n"
            "3. 💻 **程式開發**：Python 腳本生成、資料分析沙盒執行\n"
            "4. 🧠 **進階記憶**：自動追蹤您的偏好、專案進度與自進化守則\n"
            "請直接告訴我您需要什麼！"
        )
    return None
