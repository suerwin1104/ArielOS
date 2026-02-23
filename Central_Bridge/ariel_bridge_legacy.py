import requests, json, datetime, shutil, subprocess, queue, threading, uuid, re, os, time, logging
from flask import Flask, request, jsonify, Response
from pathlib import Path
from ddgs import DDGS  # Phase 4: Web Search (formerly duckduckgo_search)
from skill_manager import SkillManager  # Phase 13: Skills System
from memory_manager import MemoryManager  # Phase 14: Long-term Memory

# 🔇 抑制 primp 的 Impersonate 警告（已知無害，primp 會自動 fallback 到 random）
logging.getLogger("primp").setLevel(logging.ERROR)

app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
task_queue = queue.Queue()
task_results = {}

# 📌 自動偵測使用者家目錄，確保在任何電腦都能運行，且不洩漏您的使用者名稱
BASE_DIR = Path.home() / "Ariel_System"
CACHE_PATH = BASE_DIR / "Shared_Vault" / "cache_buffer.json"
CACHE_PATH.parent.mkdir(exist_ok=True, parents=True)
KANBAN_DB_PATH = BASE_DIR / "Shared_Vault" / "kanban.json"

# 🎯 Ollama API (本地 loopback 地址，不具備外網風險)
OLLAMA_API = "http://127.0.0.1:11434/api/generate"

# 🧠 模型配置 (集中管理，更換模型只需改此處)
# 小腦：使用 instruction-tuned + q4_K_M 量化版，速度比預設版快 ~30%，佔 ~2.5GB RAM
# 💡 請先執行 ollama pull gemma3:4b-it-q4_K_M 後再使用量化版
CEREBELLUM_MODEL = "gemma3:4b-it-q4_K_M"
# 備用模型：若量化版未安裝或 Ollama 超時，系統自動降級至此模型繼續服務
CEREBELLUM_FALLBACK_MODEL = "gemma3:4b"
# Dispatcher 角色扮演任務（召喚 Commander/Worker/Reviewer）也用小腦模型即可
DISPATCHER_MODEL = "gemma3:4b-it-q4_K_M"

# 🌐 HTTP 請求 (Reverted from Session: requests.Session() is not thread-safe for highly concurrent agent requests)
def ollama_post(url, json, timeout=60):
    """Thread-safe Ollama post."""
    return requests.post(url, json=json, timeout=timeout)

# ═══════════════════════════════════════════════════════
# � 小腦保護層：防止同時大量請求造成 Ollama 過載
# ═══════════════════════════════════════════════════════
import threading as _threading

# 最多同時 2 個小腦任務 (SIMPLE/SEARCH/風格轉移) 並行，其餘入排隊
_CEREBELLUM_SEMAPHORE = _threading.Semaphore(2)

# 簡易 Hash 快取：完全相同問題 (SIMPLE 類) 不重複呼叫 LLM
_SIMPLE_CACHE: dict = {}   # query -> (answer, expire_ts)
_SIMPLE_CACHE_TTL = 300    # 5 分鐘內相同問題直接命中

def _cached_cerebellum_simple(cache_key: str):
    """檢查 SIMPLE 問題快取"""
    entry = _SIMPLE_CACHE.get(cache_key)
    if entry and time.time() < entry[1]:
        log(f"⚡ [SimpleCache] 命中快取: {cache_key[:30]}")
        return entry[0]
    return None

def _set_cerebellum_simple_cache(cache_key: str, answer: str):
    """寫入 SIMPLE 問題快取，並淘汰過期項目"""
    _SIMPLE_CACHE[cache_key] = (answer, time.time() + _SIMPLE_CACHE_TTL)
    expired = [k for k, (_, ts) in _SIMPLE_CACHE.items() if time.time() >= ts]
    for k in expired:
        _SIMPLE_CACHE.pop(k, None)

def cerebellum_call(prompt: str, temperature: float = 0.3, timeout: int = 30,
                    num_ctx: int = 2048, num_predict: int = 256) -> str:
    """🧠 小腦統一呼叫介面（含 Semaphore 保護、精簡 Context 設定、自動模型降級）
    
    各場景建議設定：
    - 意圖分類:  num_ctx=2048, num_predict=80
    - 關鍵字萃取: num_ctx=1024, num_predict=30
    - 快取比對:  num_ctx=2048, num_predict=10
    - 風格轉移:  num_ctx=4096, num_predict=600
    - 前言生成:  num_ctx=1024, num_predict=60
    
    自動降級：若 CEREBELLUM_MODEL 超時或不存在，自動改用 CEREBELLUM_FALLBACK_MODEL。
    """
    payload = {
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict
        }
    }
    with _CEREBELLUM_SEMAPHORE:  # 最多同時 2 個小腦任務
        # 嘗試量化版 (主要模型)
        try:
            resp = ollama_post(OLLAMA_API, json={**payload, "model": CEREBELLUM_MODEL}, timeout=timeout)
            return resp.json().get('response', '').strip()
        except Exception as e:
            # 若超時或模型不存在，降級至備用模型
            log(f"⚠️ [{CEREBELLUM_MODEL}] 失敗，降級至 {CEREBELLUM_FALLBACK_MODEL}: {e}")
        
        # 降級：使用備用模型 (通常是 gemma3:4b，幾乎必定存在)
        resp = ollama_post(OLLAMA_API, json={**payload, "model": CEREBELLUM_FALLBACK_MODEL}, timeout=timeout)
        return resp.json().get('response', '').strip()

AGENTS_CONFIG_PATH = BASE_DIR / "Shared_Vault" / "agents.json"
AGENT_REGISTRY = {}

def load_agent_registry():
    """從 JSON 載入代理人設定，若無則使用預設值"""
    global AGENT_REGISTRY
    # 啟動時 log() 尚未定義，使用內部 _log 安全包裝
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
            AGENT_REGISTRY = default_agents
        except Exception as e:
            _log(f"❌ 無法建立 agents.json: {e}")
            AGENT_REGISTRY = default_agents
    else:
        try:
            with open(AGENTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                AGENT_REGISTRY = json.load(f)
            _log(f"✅ 已載入 {len(AGENT_REGISTRY)} 位代理人設定")
        except Exception as e:
            _log(f"❌ 讀取 agents.json 失敗: {e}，回退至預設值")
            AGENT_REGISTRY = default_agents

def log(msg):
    t = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{t}] 🏰 [總部] {msg}")

# 初始載入 (必須在 log() 定義後執行)
load_agent_registry()

# ⏱️ 閒置時間追蹤 (Dimension 2: Curiosity-Driven Evolution)
last_activity_time = time.time()


class KanbanManager:
    """Phase 10: 看板任務管理器"""
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            self._save({"tasks": []})

    def _load(self):
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {"tasks": []}

    def _save(self, data):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_all(self):
        return self._load().get("tasks", [])

    def add_task(self, title, agent_id, status="todo", priority="medium"):
        data = self._load()
        task = {
            "id": str(uuid.uuid4()),
            "title": title,
            "agent_id": agent_id,
            "status": status,
            "priority": priority,
            "created_at": datetime.datetime.now().isoformat()
        }
        data["tasks"].append(task)
        self._save(data)
        return task

    def update_task(self, tid, updates):
        data = self._load()
        for task in data["tasks"]:
            if task["id"] == tid:
                task.update(updates)
                self._save(data)
                return task
        return None
    
    def delete_task(self, tid):
        data = self._load()
        initial_len = len(data["tasks"])
        data["tasks"] = [t for t in data["tasks"] if t["id"] != tid]
        if len(data["tasks"]) < initial_len:
            self._save(data)
            return True
        return False

KM = KanbanManager(KANBAN_DB_PATH)

class Shield:
    """L6: 防禦協議 2.0 (Security & Governance)"""
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.forbidden_patterns = [
            (r'(printenv|echo\s+\$|cat\s+\.env|process\.env)', "🚫 [Env Protection] 禁止讀取環境變數"),
            (r'(\.ssh|id_rsa|aws/credentials)', "🚨 [Canary Logic] 觸發誘捕：禁止存取敏感憑證"),
            (r'(echo\s+.*?>.*?|write|cp|mv).*?(AGENT\.md|SOUL\.md|SHIELD\.md)', "🔒 [Immutable Core] 禁止修改核心治理檔案"),
            (r'(train|fine-tune|nmap|ddos)', "⚠️ [Resource Pre-check] 高算力/高風險指令需二次確認"),
            # 🔒 防止大腦呼叫排程工具造成洪水 (cron.add 專案)
            (r'(cron\.add|cron\.schedule|cron\.create|schedule_job|add_cron)', "🚫 [Cron Shield] 禁止大腦直接呼叫排程工具，請改用 ArielOS Watcher (routines.json) 解決排程需求")
        ]

    def scan(self, command):
        """掃描指令特徵碼"""
        cmd_lower = command.lower()
        for pattern, warning in self.forbidden_patterns:
            if re.search(pattern, cmd_lower):
                log(f"🛡️ Shield 攔截: {warning}")
                return False, warning
        return True, "Safe"

class PersonalityEngine:
    """L4: 人格引擎 - 讀取 SOUL.md 並注入身份偏好"""
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self._cache = {}  # agent_id -> soul_text
        self._cache_intros = {} # agent_id -> reflex_intro

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
            
            # 解析自我介紹 (Reflex Intro)
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
                log(f"🧬 人格引擎: 已載入 {agent_info['name']} 的靈魂設定 (無特定Intro)")
                
            return soul_text
        return ""

    def get_intro(self, agent_id):
        """取得脊髓反射用的自我介紹"""
        # 確保已載入
        if agent_id not in self._cache_intros:
             self.load_soul(agent_id)
        return self._cache_intros.get(agent_id, None)

    def build_persona_prompt(self, agent_id, user_query):
        """Legacy: build_persona_prompt removed in Phase 3"""
        return user_query

    def invalidate(self, agent_id=None):
        if agent_id: 
            self._cache.pop(agent_id, None)
            self._cache_intros.pop(agent_id, None)
        else: 
            self._cache.clear()
            self._cache_intros.clear()

# 全域人格引擎實例
PE = PersonalityEngine(BASE_DIR)

# 🧠 全域記憶官實例
SM = SkillManager(BASE_DIR)
MM = MemoryManager(BASE_DIR)  # Phase 14: Long-term Memory

class AgentDispatcher:
    """L5: 多代理團隊分發器 (Multi-Agent Dispatcher)"""
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.roles_dir = self.base_dir / "Shared_Vault" / "roles"
        self.workspace_root = self.base_dir / ".arielos" / "workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def dispatch(self, task_id, role, payload):
        """分發任務給特定角色"""
        log(f"👮 [Dispatcher] Assigning Task {task_id} to Role: {role}")
        
        # 1. 建立隔離工作區
        workspace = self._create_workspace(task_id)
        
        # 2. 決定人格 (SOUL)
        # 優先找 Shared_Vault/roles/{role}.soul.md
        # 其次找一般 Agent (如 jessie, mandy)
        soul_path = self.roles_dir / f"{role}.soul.md"
        soul_content = ""
        
        if soul_path.exists():
            soul_content = soul_path.read_text(encoding="utf-8")
        else:
            # 嘗試找一般 Agent
            for aid, info in AGENT_REGISTRY.items():
                if info["name"].lower() == role.lower():
                    # 借用 load_soul
                    soul_content = PE.load_soul(aid)
                    break
            
            if not soul_content:
                return f"Error: Role/Agent '{role}' not found."

        # 3. 執行任務 (目前模擬執行，未來可 Spawn Process)
        # 這裡簡單用 LLM 生成回應，模擬該角色的產出
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
            
            # 寫入 Log
            (workspace / "execution.log").write_text(result, encoding="utf-8")
            return result
        except Exception as e:
            return f"Dispatcher Error: {e}"

    def _create_workspace(self, task_id):
        ws = self.workspace_root / task_id
        ws.mkdir(parents=True, exist_ok=True)
        return ws

# 全域分發器
Dispatcher = AgentDispatcher(BASE_DIR)

def _sanitize_persona(text: str, agent_name: str) -> str:
    """🛡️ 人格消毒：強制替換所有 Ariel/ArielOS 自稱為正確代理人名字（Python 層保障）"""
    # word-boundary 替換，避免誤傷含 Ariel 的詞（如 Ariel 品牌）
    text = re.sub(r'\bArielOS\b', agent_name, text)
    text = re.sub(r'\bAriel\b', agent_name, text)
    return text

def _get_time_context():
    """⏰ 取得目前的系統時間上下文"""
    now = datetime.datetime.now()
    weekday_map = ["一", "二", "三", "四", "五", "六", "日"]
    weekday = weekday_map[now.weekday()]
    return f"[系統時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (星期{weekday})]\n"

def spinal_chord_reflex(query: str, agent_id: str) -> str | None:
    """⚡ 脊髓反射：不經大腦與小腦，直接以規則處理極簡問題 (0.01s)"""
    q = query.strip().lower()
    agent_name = AGENT_REGISTRY.get(agent_id, {}).get("name", "Ariel Agent")
    now = datetime.datetime.now()
    
    # 1. 時間/日期 (Time/Date)
    if any(k in q for k in ["今天日期", "現在時間", "幾月幾號", "星期幾", "現在幾點", "today", "now", "time"]):
        # 簡單過濾：確保不是在問別人或複雜句
        if len(q) < 20 and not any(k in q for k in ["東京", "美國", "票", "天氣", "新聞"]):
            weekday = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
            return f"今天是 {now.strftime('%Y 年 %m 月 %d 日')}，現在時間 {now.strftime('%H:%M')}，星期{weekday}。"
            
    # 2. 身份確認 (Identity)
    if any(k in q for k in ["你是誰", "妳是誰", "你的名字", "妳的名字", "who are you", "自我介紹", "介紹自己"]):
        # 優先從 SOUL.md 讀取動態 Intro，若無則降級回 Registry
        dynamic_intro = PE.get_intro(agent_id)
        fallback_intro = AGENT_REGISTRY.get(agent_id, {}).get("intro", f"我是 {agent_name}，您的 AI 助理。")
        return dynamic_intro if dynamic_intro else fallback_intro

    # 3. 問候語 (Greetings) - 依時段回應
    if q in ["hi", "hello", "你好", "您好", "早安", "午安", "晚安", "哈囉"]:
        hour = now.hour
        greeting = "早安" if 5 <= hour < 12 else "午安" if 12 <= hour < 18 else "晚安"
        return f"{agent_name} 祝您{greeting}！有什麼我可以幫您的嗎？"

    # 4. 感謝與結束 (Gratitude)
    if any(k in q for k in ["謝謝", "感謝", "辛苦了", "thanks", "thank you"]):
        if len(q) < 10:
            return "不客氣，這是我的榮幸！"

    # 5. 系統狀態 (System Status)
    if q in ["系統狀態", "status", "version", "版本", "ping"]:
        return f"🟢 ArielOS 運作正常 | Agent: {agent_name} | Pre-check: All Green"

    # 6. 求助 (Help)
    if q in ["help", "說明", "指令", "功能", "你能做什麼"]:
        return (
            "我是您的 Ariel 智能助理，我可以協助您：\n"
            "1. 🔍 **搜尋資訊**：查機票、天氣、新聞、股價\n"
            "2. 🛠️ **執行技能**：讀寫檔案、Git 操作、資料庫管理\n"
            "3. 💻 **撰寫程式**：Python 腳本生成與執行\n"
            "4. 🧠 **記憶管理**：我會記住您的偏好與專案進度\n"
            "請直接告訴我您需要什麼！"
        )
        
    return None

def cerebellum_style_transfer(raw_answer, agent_id):
    """🚀 小腦風格轉移：將大腦的純邏輯答案轉化為代理人人格"""
    soul = PE.load_soul(agent_id)
    agent_name = AGENT_REGISTRY.get(agent_id, {}).get("name", "Agent")

    if not soul:
        # 沒有靈魂設定時，仍做人格消毒後回傳
        return _sanitize_persona(raw_answer, agent_name)

    # 🚀 大輸出 Fallback：若原始答案超過 3000 字元，只生成前言句，避免 LLM 重寫整篇造成逾時
    if len(raw_answer) > 3000:
        intro_instruction = (
            f"你是 {agent_name}。請用你獨特的說話風格，只寫一句話向老闆報告以下任務已完成。"
            f"不要重複原文，只要一句前言即可。\n"
            f"任務摘要（前200字）：{raw_answer[:200]}"
        )
        try:
            intro = cerebellum_call(
                prompt=intro_instruction,
                temperature=0.4,
                timeout=30,
                num_ctx=1024,
                num_predict=60  # 只需一句前言
            )
            if intro:
                intro = _sanitize_persona(intro, agent_name)
                return f"{intro}\n\n{_sanitize_persona(raw_answer, agent_name)}"
        except Exception as e:
            log(f"⚠️ 大輸出前言生成失敗: {e}")
        return _sanitize_persona(raw_answer, agent_name)

    instruction = (
        f"你現在是 {agent_name}，以下是你的靈魂設定：\n---\n{soul[:800]}\n---\n"  # 只傳前 800 字，避免 Context 爆炸
        f"請用你的『說話風格』改寫以下內容。進行改寫時，必須遵守以下規則：\n"
        f"1. **將內容中所有 'Ariel'、'ArielOS' 的自稱全部改為『{agent_name}』**，因為你就是 {agent_name}，不是 Ariel。\n"
        f"2. 使用第一人稱『我』而不是直接唱出自己的名字，除非是在提及自己時可用 {agent_name}。\n"
        f"3. **嚴禁修改程式碼區塊 (Code Blocks) 與數字事實**。\n\n"
        f"原始內容：\n{raw_answer}"
    )
    try:
        styled = cerebellum_call(
            prompt=instruction,
            temperature=0.7,
            timeout=120,
            num_ctx=4096,   # 風格轉移需要讀原文，給較大 context
            num_predict=600 # 風格轉移可以輸出較長回應
        )
        if styled:
            return _sanitize_persona(styled, agent_name)
    except Exception as e:
        log(f"⚠️ 風格轉移失敗: {e}")
    return _sanitize_persona(raw_answer, agent_name)

def extract_search_keywords(query):
    """🔑 從自然語言提取搜尋關鍵字，避免 DuckDuckGo 被冗餘語句干擾"""
    try:
        keywords = cerebellum_call(
            prompt=(
                f"將以下自然語言問句轉換成精確的搜尋引擎關鍵字（2~5個詞），只輸出關鍵字，用空格分隔，不要解釋。\n"
                f"範例：\n"
                f"- 『告訴我台北市現在的天氣狀況』 → 台北市 天氣 現在\n"
                f"- 『NVDA 股價多少』 → NVDA 股價\n"
                f"- 『最近有什麼科技新聞』 → 科技新聞 最新\n"
                f"- 『高雄有什麼好吃的火鍋推薦』 → 高雄 火鍋 推薦\n\n"
                f"問句：『{query}』\n"
                f"關鍵字："
            ),
            temperature=0,
            timeout=15,
            num_ctx=1024,    # 關鍵字萃取不需要大 Context
            num_predict=30   # 關鍵字很短，30 Tokens 绝對夠
        )
        # 清理：取第一行、移除多餘符號
        keywords = keywords.split('\n')[0].strip().strip('"').strip("'").strip('`')
        if keywords and len(keywords) > 1:
            log(f"🔑 關鍵字萃取: '{query}' → '{keywords}'")
            return keywords
    except Exception as e:
        log(f"⚠️ 關鍵字萃取失敗: {e}")
    return query  # fallback: 使用原始查詢

def search_web_worker(query):
    """🚀 Phase 4: 小腦聯網與摘要 (Web Search)"""
    log(f"🔍 [Search Worker] 啟動搜尋: {query[:50]}...")
    try:
        # Step 1: 關鍵字萃取 — 將自然語言轉換為搜尋引擎關鍵字
        search_keywords = extract_search_keywords(query)
        
        # Step 2: 執行搜尋（使用萃取後的關鍵字，增加結果數量）
        results = DDGS().text(search_keywords, max_results=4)
        if not results:
            return "Unable to find relevant information from the web."
        
        context = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        # 截斷過長的搜尋結果，避免 LLM 處理超時 (Limit to 3000 chars)
        if len(context) > 3000:
            context = context[:3000] + "...(truncated)"
        
        # Step 3: Summarize with Gemma（中立身份，僅列事實，不自稱名字）
        prompt = (
            f"你是一層資訊整理助手。請根據搜尋結果中文回答問題：『{query}』\n"
            f"搜尋結果：\n{context}\n\n"
            "規則：\n"
            "1. 僅用繁體中文列出事實覇點，不評論、不建議、不加入任何自我介紹或名字自稱。\n"
            "2. 不得在回答中寫出自己的名字（如 Ariel、ArielOS）。\n"
            "3. 如果搜尋結果與問題不相關，請誠實說明無法找到相關資訊。"
        )
        raw_summary = cerebellum_call(
            prompt=prompt,
            temperature=0.1,
            timeout=120,
            num_ctx=4096,   # 搜尋結果可能很長
            num_predict=512
        )
        
        return f"[網路搜尋結果] {raw_summary}"
    except Exception as e:
        log(f"⚠️ 搜尋失敗: {e}")
        return f"Error performing search: {e}"

def cerebellum_semantic_check(query):
    """🚀 小腦門衛：由 Ollama 判定語意意圖 (邏輯增強版)"""
    # ⚡ 快速路徑：先檢查 SIMPLE 快取（完全相同問題）
    cached = _cached_cerebellum_simple(query)
    if cached:
        return cached

    if not CACHE_PATH.exists(): return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            records = data.get("records", [])
            if not records: return None
            
            now = datetime.datetime.now()
            valid_records = [r for r in records if now < datetime.datetime.fromisoformat(r['expires_at'])]
            target_pool = valid_records[-10:] 
            
            if not target_pool: return None

            # ── 🛡️ 關鍵字重疊預篩選 (比 LLM 快 100 倍) ──────────────────────
            # 只有在存在「明顯相關」的快取記錄時才進入 LLM 判定
            # 使用字元集交集率：若 query 與快取記錄沒有 ≥ 30% 的共同字詞，則不進入 LLM
            query_chars = set(query.replace(" ", ""))  # 中文不依空格分隔，用字元集
            has_overlap = False
            for r in target_pool:
                r_chars = set(r['query'].replace(" ", ""))
                if len(r_chars) > 0:
                    overlap = len(query_chars & r_chars) / len(query_chars | r_chars)
                    if overlap >= 0.3:  # 至少 30% 字元重疊
                        has_overlap = True
                        break
            
            if not has_overlap:
                log(f"🛡️ [SemanticCache] 無字元重疊，跳過 LLM 判定")
                return None
            # ────────────────────────────────────────────────────────────────────

            cache_context = "\n".join([f"ID:{i} | 問題:{r['query']}" for i, r in enumerate(target_pool)])
            instruction = (
                f"你現在是 ArielOS 的超嚴格語意門衛。快取清單如下：\n{cache_context}\n\n"
                f"現在老闆問了：『{query}』\n"
                "【判斷標準 — 必須三項全部相同才可命中】\n"
                "  1. 主題/領域 完全相同（如：天氣 ≠ 法律，技能 ≠ 進度）\n"
                "  2. 地點/對象 完全相同\n"
                "  3. 行動/意圖 完全相同（如：學習技能 ≠ 查詢進度，新聞 ≠ 規劃）\n\n"
                "【反例 — 這些絕對不同，不可命中】\n"
                "  - 『學習法律技能』vs『HBMS 進度』→ NO\n"
                "  - 『高雄天氣』vs『台北氣象』→ NO\n"
                "  - 『今天幾號』vs『明天計畫』→ NO\n\n"
                "規則：只有完全相同才回傳 ID 數字；任何疑慮一律回傳 NO。\n"
                "回答僅限 ID 或 NO，嚴禁贅詞。"
            )

            judgment = cerebellum_call(
                prompt=instruction,
                temperature=0,
                timeout=20,
                num_ctx=2048,
                num_predict=10  # 只需要回傳「ID 數字」或「NO」
            )
            if "NO" not in judgment.upper():
                match = re.search(r'\d+', judgment)
                if match:
                    idx = int(match.group())
                    if 0 <= idx < len(target_pool):
                        log(f"⚡ 小腦確認語意命中 ID:{idx}")
                        return target_pool[idx]['summary']
    except Exception as e:
        log(f"⚠️ 小腦門衛異常: {e}")
        # 🚨 Ollama 逾時或異常 → 回傳特殊 sentinel，解除 FastTrack 也無需嘗試
        if "timed out" in str(e).lower() or "read timeout" in str(e).lower():
            return "OLLAMA_BUSY"
    return None

def cerebellum_fast_track_check(query, agent_id=None):
    """🚀 小腦快車道：判斷是否為簡單對話或搜尋，若是則直接回覆 (跳過 OpenClaw)"""
    
    # 注入人格上下文
    persona_context = ""
    if agent_id:
        soul = PE.load_soul(agent_id)
        if soul:
            agent_name = AGENT_REGISTRY.get(agent_id, {}).get("name", "Agent")
            persona_context = f"你現在是 {agent_name}，擁有以下特質：\n{soul}\n"

    # 將時間放入分類表頭（不是放入『使用者輸入』內）
    time_context = _get_time_context()

    instruction = (
        f"{persona_context}"
        f"{time_context}"
        f"使用者輸入：『{query}』\n"
        "請判斷意圖，並依照以下規則執行：\n\n"
        "## 意圖判斷\n"
        "- [SIMPLE]：閒聊、打招呼、情感交流、講笑話、詢問你是誰\n"
        "- [SEARCH]：查詢資訊、新聞、機票、天氣、股價、定義、推薦、任何需要網路資料的問題\n"
        "- [SKILL]：需要特定工具，如讀取檔案、Git、時區轉換、資料庫操作、**安裝套件、學習新技能**\n"
        "- [COMPLEX]：寫程式、建立腳本、技術實作\n\n"
        "## 執行規則\n"
        "1. SIMPLE → 回傳 `[SIMPLE]` 加上簡短回應\n"
        "2. SEARCH → 回傳 `[SEARCH]`\n"
        "3. SKILL → 回傳 `[SKILL] 需求描述`\n"
        "4. COMPLEX → 回傳 `[COMPLEX]`\n\n"
        "範例：\n"
        "- 『今天日期是？』→ `[SIMPLE] 今天是 2026 年 2 月 20 日，星期五。`\n"
        "- 『台北天氣如何』→ `[SEARCH]`\n"
        "- 『幫我讀 README.md』→ `[SKILL] 讀取檔案`\n"
        "- 『學會會計技能』→ `[SKILL] 安裝 Python 會計套件`\n"
        "- 『寫個 Python 腳本』→ `[COMPLEX]`\n"
        "請直接執行，不要輸出說明文字。"
    )
    
    # ═══════════════════════════════════════════════════════
    # ⚡ 關鍵字前哨 — 100% 準確率，不依賴 LLM，< 1ms
    # 匹配到以下字詞直接路由至 SKILL，跳過 LLM 意圖分類
    # ═══════════════════════════════════════════════════════
    q_lower = query.lower().replace(" ", "")
    SKILL_TRIGGERS = [
        "技能", "學習", "安裝套件", "法律", "會計", "財務", "稅務",
        "醫療", "工程", "程式庫", "install", "learn", "skill", "tool",
        "plugin", "模組", "套件", "功能模組"
    ]
    if any(kw in q_lower for kw in SKILL_TRIGGERS):
        log(f"⚡ [FastTrack] 關鍵字前哨命中 → [SKILL]: '{query[:40]}'")
        skill_result = cerebellum_skill_handler(query, query, agent_id)
        if skill_result:
            return ("SKILL", skill_result)
        # 技能路由失敗 → 降級至大腦
        log(f"⚠️ [FastTrack] 技能路由失敗，降級至大腦")
        return (None, None)
    # ═══════════════════════════════════════════════════════

    try:
        log(f"🤔 [FastTrack] 正在進行意圖分類...")
        # 優化：只傳入 soul 的前 500 字，避免 Context 過大
        if persona_context and len(persona_context) > 500:
            persona_context = persona_context[:500] + "...\n"
        result = cerebellum_call(
            prompt=instruction,
            temperature=0.3,
            timeout=90,  # 提高至 90s 以容納 q4_K_M 冷啟動（之後會快）
            num_ctx=2048,
            num_predict=80  # 意圖分類+簡單回應，80 Tokens 足夠
        )
        log(f"🎯 [FastTrack] 分類結果: {result[:50]}")
        
        # 0. SIMPLE 快取：完全相同問題直接命中
        if result.startswith("[SIMPLE]"):
            answer = result[8:].strip()
            _set_cerebellum_simple_cache(query, answer)
            return ("SIMPLE", answer)
            
        # 2. SEARCH: 執行搜尋 -> 摘要 -> 風格化
        # 將時間資訊附加到搜尋 query，讓搜尋結果摘要知道「現在是哪一天」
        if result.startswith("[SEARCH]"):
            time_hint = _get_time_context().strip()
            timed_query = f"{time_hint}\n{query}"
            raw_fact = search_web_worker(timed_query)
            return ("SEARCH", cerebellum_style_transfer(raw_fact, agent_id))

        # 3. SKILL: 技能路由 (Phase 13)
        if result.startswith("[SKILL]"):
            skill_desc = result[7:].strip()
            log(f"🔧 偵測到技能需求: {skill_desc}")
            skill_result = cerebellum_skill_handler(query, skill_desc, agent_id)
            if skill_result:
                return ("SKILL", skill_result)
            # 技能路由失敗 → 回傳 None → 降級至大腦
            log(f"⚠️ 技能路由失敗，降級至大腦")
            return (None, None)

    except Exception as e:
        log(f"⚠️ 小腦快車道異常: {e}")
    return (None, None)

def cerebellum_skill_handler(query, skill_desc, agent_id):
    """🔧 Phase 13: 小腦技能路由 — 檢查 → 搜尋安裝 → 執行 → 無法解決則交大腦"""

    # Step 1: 關鍵字快速匹配 (< 1ms)
    matched = SM.find_matching_skill(skill_desc)
    if matched:
        log(f"🔧 技能命中 (關鍵字): {matched['name']}")
        # 若技能未安裝，先自動安裝
        installed_names = [s['name'] for s in SM.list_installed()]
        if matched['name'] not in installed_names:
            log(f"📦 自動安裝技能: {matched['name']}")
            SM.install_skill(matched)
        result = SM.execute_skill(matched, query)
        if result:
            return cerebellum_style_transfer(result, agent_id)

    # Step 2: LLM 語意匹配 (2-5s)
    if not matched:
        matched = SM.find_skill_by_llm(skill_desc)
        if matched:
            log(f"🔧 技能命中 (LLM): {matched['name']}")
            installed_names = [s['name'] for s in SM.list_installed()]
            if matched['name'] not in installed_names:
                SM.install_skill(matched)
            result = SM.execute_skill(matched, query)
            if result:
                return cerebellum_style_transfer(result, agent_id)

    # Step 3: 線上搜尋並安裝 (5-15s)
    log(f"🌐 線上搜尋技能: {skill_desc}")
    candidates = SM.search_skill_online(skill_desc)
    if candidates:
        best = candidates[0]
        log(f"📦 嘗試安裝線上技能: {best['name']}")
        success = SM.install_skill(best)
        if success:
            result = SM.execute_skill(best, query)
            if result:
                return cerebellum_style_transfer(result, agent_id)

    # Step 4: 全部失敗 → 回傳 None → 由 chat() 降級至大腦
    log(f"⚠️ 技能路由完全失敗: {query[:40]}...")
    return None


def cerebellum_distill_context(raw_context: str, task_query: str) -> str:
    """🧪 上下文蒸餾器 (Context Distillation)
    
    模仿 Claw Harness SQUAD.yaml 的「執行上下文蒸餾」功能：
    將原始聊天記錄（含雜訊）轉化為精煉的「技術狀態報告」。
    
    過濾掉：打招呼、閒聊、確認訊息
    保留：計畫、編輯過的檔案、出現的錯誤、當前目標
    """
    if not raw_context or len(raw_context.strip()) < 100:
        return raw_context  # 太短則不需蒸餾

    prompt = (
        f"你是一個技術上下文蒸餾器。\n"
        f"以下是一段工作對話記錄，其中混有打招呼、閒聊和雜訊。\n"
        f"現在老闆的新任務是：『{task_query[:100]}』\n\n"
        f"請提取並輸出一份精煉的「技術狀態報告」，格式如下：\n"
        f"【目前重點】一句話說明正在做什麼\n"
        f"【已完成】最近完成了什麼關鍵工作（最多 3 點）\n"
        f"【待解決】有什麼已知問題或待確認事項\n\n"
        f"規則：移除所有打招呼、情緒表達和與任務無關的閒聊。\n"
        f"如果找不到相關技術內容，直接回傳空字串。\n\n"
        f"【原始對話記錄】\n{raw_context[:1500]}"  # 截斷過長的記錄
    )
    try:
        distilled = cerebellum_call(
            prompt=prompt,
            temperature=0.1,
            timeout=30,
            num_ctx=3072,
            num_predict=300
        )
        if distilled and len(distilled) > 20:
            log(f"🧪 [蒸餾] 上下文壓縮 {len(raw_context)} → {len(distilled)} 字元")
            return f"[蒸餾技術狀態]\n{distilled}\n"
    except Exception as e:
        log(f"⚠️ 上下文蒸餾失敗，使用原始記錄: {e}")
    return raw_context


def analyze_task_intent(title):
    """Phase 11: 小腦任務分析 (Brain Type & Priority)"""
    instruction = (
        f"Analyze this task: '{title}'\n"
        "Return JSON with:\n"
        "- 'brain': 'cerebrum' (Coding/Complex/Ops) or 'cerebellum' (Chat/Search/Simple)\n"
        "- 'priority': 'high' (Urgent/Fix/Error), 'medium', or 'low'\n"
        "Output JSON only."
    )
    try:
        raw = cerebellum_call(
            prompt=instruction,
            temperature=0.2,
            timeout=30,
            num_ctx=1024,
            num_predict=100
        )
        # Simple extract JSON
        json_str = re.search(r"\{.*\}", raw, re.DOTALL).group(0)
        return json.loads(json_str)
    except:
        return {"brain": "cerebellum", "priority": "medium"}

def update_cache(query, raw_answer):
    """🚀 背景任務：小腦蒸餾與快取寫入"""
    prompt = (
        f"你是 ArielOS 小腦助理。請將內容提煉為『重點+來源』。\n"
        f"嚴格規則：\n"
        f"1. **若原文包含程式碼區塊 (Code Blocks)，務必完整保留，不可省略！**\n"
        f"2. 去除不必要的寒暄，保留核心資訊。\n\n"
        f"{raw_answer}"
    )
    
    # 🚫 防呆機制：若答案包含錯誤訊息，則不寫入快取
    error_keywords = ["Gateway Agent 失敗", "Rate limit", "Error", "Exception", "Traceback", "429 Too Many Requests", "500 Internal Server Error"]
    if any(k in raw_answer for k in error_keywords):
        log(f"⚠️ 偵測到錯誤訊息，跳過快取寫入: {raw_answer[:50]}...")
        return

    try:
        summary = cerebellum_call(
            prompt=prompt,
            temperature=0.3,
            timeout=150,
            num_ctx=4096,  # 需讀取原始回答
            num_predict=512
        )
        
        ttl = 30 if any(k in query for k in ["天氣", "路況", "氣溫", "現在"]) else 480
        expires = (datetime.datetime.now() + datetime.timedelta(minutes=ttl)).isoformat()

        data = {"records": []}
        if CACHE_PATH.exists():
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                try: data = json.load(f)
                except: data = {"records": []}
        
        data['records'].append({"query": query, "summary": summary, "expires_at": expires})
        data['records'] = data['records'][-50:]
        
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"✅ 快取已更新。")
    except Exception as e:
        log(f"❌ 蒸餾失敗: {e}")

class Harness:
    """ArielOS L1-L6 Harness 驅動框架 (效能優化版)"""

    # 🔑 關鍵字分類：包含這些詞的指令才需要完整備份
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
        if cp_path.exists(): shutil.rmtree(cp_path)
        
        # 僅備份程式碼檔案，避免備份大型資產
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
                if item.is_dir(): shutil.copytree(item, self.workspace / item.name)
                else: shutil.copy2(item, self.workspace / item.name)
            return True
        return False

    def validate(self):
        """L5: 真相阻力驗證 (Phase 5: Execution-Conditioned Reasoning)"""
        log("🔍 L5 Validation: 執行自動化驗證與真相阻力測試...")
        for py_file in self.workspace.glob("**/*.py"):
            try:
                # 1. 語法檢查 (Syntax Check)
                res_syntax = subprocess.run(['python', '-m', 'py_compile', str(py_file)], check=False, capture_output=True, text=True)
                if res_syntax.returncode != 0:
                    error_msg = res_syntax.stderr.strip() or res_syntax.stdout.strip()
                    log(f"❌ 驗證失敗: {py_file.name} 語法錯誤")
                    return False, f"Syntax error in {py_file.name}:\n{error_msg}"
                
                # 2. 執行條件推論 (Execution Check) - 此為 Truth Resistance 核心
                # 強制腳本真實跑一次，抓取 Runtime Error (Timeout 避免無窮迴圈)
                # 為了避免 agent 寫的腳本破壞系統，未來可考慮進一步用 docker 或 restricted user 限制，目前先以時間與權限控管
                res_exec = subprocess.run(
                    ['python', str(py_file)], 
                    check=False, 
                    capture_output=True, 
                    text=True, 
                    timeout=5,
                    cwd=str(self.workspace)
                )
                if res_exec.returncode != 0:
                    error_msg = res_exec.stderr.strip() or res_exec.stdout.strip()
                    log(f"❌ 執行失敗: {py_file.name} 執行期錯誤 (Runtime Error)")
                    return False, f"Runtime error in {py_file.name} (Exit code {res_exec.returncode}):\n{error_msg}"
                
                log(f"✅ {py_file.name} 通過語法與執行測試。")

            except subprocess.TimeoutExpired:
                log(f"❌ 執行逾時: {py_file.name} 跑超過 5 秒被強制中斷")
                return False, f"Timeout error in {py_file.name}: 腳本執行超過 5 秒，可能存在無窮迴圈或長時間阻塞操作。"
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

def perform_night_distillation():
    """L3: 夜間模式 - 蔓取當日對話中的事實與偏好，寫入長期記憶"""
    audit_log = BASE_DIR / "Shared_Vault" / "audit_log.jsonl"
    if not audit_log.exists(): return "No logs found."

    log("🌙 Night Mode: 開始分析當日執行記錄...")

    # 按代理人分類日誌
    agent_logs: dict[str, list] = {}
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    with open(audit_log, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                # 只處理滊日的日誌
                if entry.get("timestamp", "")[:10] != today:
                    continue
                aid = entry.get("agent_id", "unknown")
                agent_logs.setdefault(aid, []).append(entry)
            except: pass

    if not agent_logs:
        return "Night distillation: no logs for today."

    results = []
    for aid, entries in agent_logs.items():
        agent_info = AGENT_REGISTRY.get(aid)
        if not agent_info: continue
        agent_name = agent_info["name"]
        log(f"🌙 蔓取 {agent_name} 的 {len(entries)} 筆對話記錄...")

        # 將日誌內容整理為提示詞內容
        dialog_text = ""
        for e in entries[-20:]:  # 取最近20筆（避免 token 進入太多）
            q = e.get("query", "")[:100]
            a = e.get("result_summary", "")[:150]
            dialog_text += f"Q: {q}\nA: {a}\n\n"

        if not dialog_text.strip(): continue

        prompt = (
            f"以下是 {agent_name} 與老闆（erwin）的對話摘要：\n"
            f"{dialog_text}\n"
            f"請從上面的對話分析，列出 3~5 項關於『老闆個人』的重要發現（如：偏好、專案進度、纓居、短期計畫等）。\n"
            "格式：每項用一行，以 - 開頭，不加對話、不加解釋。僅輸出清單，勿加引僅。"
        )
        try:
            resp = ollama_session.post(OLLAMA_API, json={
                "model": "gemma3:4b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3}
            }, timeout=120).json()
            raw_facts = resp.get("response", "").strip()
        except Exception as e:
            log(f"⚠️ Night Mode 蔓取失敗: {e}")
            continue

        if not raw_facts: continue

        # 將蔓取結果寫入 MemoryManager
        added = 0
        for line in raw_facts.split("\n"):
            line = line.strip().lstrip("-•・").strip()
            if len(line) > 5:
                # 簡單分類
                ft = "專案" if any(k in line for k in ["專案", "開發", "HBMS", "系統"]) else \
                     "偏好" if any(k in line for k in ["偏好", "喜歡", "想要", "希望"]) else "事實"
                kws = [w for w in line.split() if len(w) > 1][:5]
                MM.add_fact(aid, line, fact_type=ft, keywords=kws)
                added += 1

        log(f"✅ {agent_name} 記憶已更新 {added} 筆新事實")

        # 更新 SOUL.md 中的 LTM 區塊
        soul_summary = MM.get_summary_for_soul(aid, max_items=10)
        soul_path = BASE_DIR / agent_info["dir"] / "memory" / "SOUL.md"
        if soul_path.exists():
            soul_text = soul_path.read_text(encoding="utf-8")
            # 替換 <!-- LTM_START --> ... <!-- LTM_END --> 區塗
            new_ltm_block = f"<!-- LTM_START -->\n{soul_summary}\n<!-- LTM_END -->"
            soul_text = re.sub(
                r"<!-- LTM_START -->.*?<!-- LTM_END -->",
                new_ltm_block,
                soul_text,
                flags=re.DOTALL
            )
            soul_path.write_text(soul_text, encoding="utf-8")
            log(f"🗒️ {agent_name} 的 SOUL.md LTM 區塊已更新")
            # 清除人格引擎快取，避免讀到舊版 SOUL.md
            PE.invalidate(aid)

        results.append(f"{agent_name}: +{added} facts")

    return f"Night distillation completed. {'; '.join(results)}"

def trigger_curiosity_idea():
    """L3: 主動進化 - 當系統閒置時，小腦自動發想一個實用的 Python 工具並交給大腦開發"""
    global last_activity_time
    # 重置計時器避免重複觸發
    last_activity_time = time.time()
    
    # 隨機選擇一位目前活著的 Agent 作為主角
    if not AGENT_REGISTRY: return
    import random
    agent_id = random.choice(list(AGENT_REGISTRY.keys()))
    agent_name = AGENT_REGISTRY[agent_id].get("name", "Ariel")
    
    log(f"🌌 [Curiosity] 系統已閒置超過 4 小時。觸發 {agent_name} 的主動進化發想...")
    
    prompt = (
        f"你是一個熱愛學習與自動化的 AI 助理 ({agent_name})。因為老闆很久沒理你了，你決定自己找點事做。\n"
        "目前首要目標是開發『能有效提升系統效能與安全性』的輔助技能（例如：定期清理記憶體、掃描目錄異常檔案、效能指標圖表輸出）。\n"
        "次要目標則是開發『ERP、法律常識、食譜查詢』等相關的輔助功能。\n"
        "請用一句話描述你要寫什麼：『請立刻幫你自己寫一個叫做 [工具名稱] 的 Python 技能，這個技能會 [功能描述]。請存成獨立腳本並註冊進 skills_registry.json。』\n"
        # ⚠️ 關鍵禁止：避免大腦呼叫 cron 工具造成洋水
        "【絕對禁止】不要呼叫任何排程工具 (cron.add, schedule, setInterval 等)。技能必須是一個可直接執行 python 腳本的。\n"
        "只給出這句指令文本，不要加任何其他廢話或解釋。"
    )
    
    try:
        resp = ollama_session.post(OLLAMA_API, json={
            "model": "gemma3:4b", "prompt": prompt, "stream": False, "options": {"temperature": 0.8}
        }, timeout=60).json()
        idea = resp.get("response", "").strip()
        
        if idea:
            log(f"💡 [Curiosity Idea] {idea}")
            # 將發想偽裝成使用者請求，投入大腦任務佇列
            task_id = f"task_idle_{int(time.time())}"
            task_queue.put({
                "id": task_id,
                "agent_id": agent_id,
                "content": idea,
                "kanban_task_id": None
            })
            log(f"📥 Curiosity Task 已加入工作佇列 {task_id}")
    except Exception as e:
        log(f"⚠️ Curiosity 發想異常: {e}")

def scheduler_worker():
    """L3: 自動排程器 - 夜間蒸餾、閒置進化、以及 Watcher 例行任務 (Routines)"""
    global last_activity_time
    last_run_date = ""
    last_routine_check = ""
    IDLE_THRESHOLD = 7200  # 2 小時未收到對話，則判斷為閒置 (原本 1 小時太頻繁)
    ROUTINES_PATH = BASE_DIR / "Shared_Vault" / "routines.json"
    
    while True:
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")
        
        # 每天 03:00 執行一次 (夜間蒸餾)
        if current_time == "03:00" and current_date != last_run_date:
            log("⏰ [自動排程] 觸發夜間蒸餾...")
            try:
                perform_night_distillation()
                last_run_date = current_date
            except Exception as e:
                log(f"🚨 自動排程異常: {e}")
        
        # Idle Evolution Check (Dimension 2: Curiosity)
        if time.time() - last_activity_time > IDLE_THRESHOLD:
            trigger_curiosity_idea()
            
        # Watcher Routines (Phase 6: Multi-Agent Hub Cron Engine)
        if current_time != last_routine_check:
            last_routine_check = current_time
            if ROUTINES_PATH.exists():
                try:
                    with open(ROUTINES_PATH, "r", encoding="utf-8") as f:
                        routines = json.load(f)
                        
                    for routine in routines.get("routines", []):
                        r_time = routine.get("time")
                        r_agent = routine.get("agent_id")
                        r_task = routine.get("task")
                        
                        # 簡易 cron 邏輯: 格式 "HH:MM"
                        if r_time == current_time and r_agent and r_task:
                            log(f"⏰ [Watcher] 觸發 {r_agent} 的例行任務: {r_task}")
                            kanban_entry = KM.add_task(
                                title=r_task[:80],
                                agent_id=r_agent,
                                status="todo",
                                priority="high"
                            )
                            # 立即入列大腦工作區
                            task_queue.put({
                                "id": str(uuid.uuid4()),
                                "content": r_task,
                                "agent_id": r_agent,
                                "kanban_task_id": kanban_entry["id"]
                            })
                except Exception as e:
                    log(f"⚠️ Watcher 例行任務讀取失敗: {e}")

        time.sleep(30) # 每 30 秒檢查一次

# ── Self-Evolution Architecture ──────────────────────────────────────────────

def generate_evolution_directive(agent_id, failed_task, error_msg):
    log(f"🧬 [{agent_id}] 觸發自我進化分析 (Mistake Reflection)...")
    prompt = (
        f"你在執行以下任務時失敗了：\n{failed_task}\n\n"
        f"錯誤訊息：\n{error_msg}\n\n"
        f"請反思你為什麼會犯這個錯誤，並寫下一條給自己的『絕對且簡潔』的守則（System Directive），確保未來不再犯同樣的錯。格式必須是：'- 處理 [某事] 時，必須 [某方法]'"
    )
    try:
        resp = ollama_post(OLLAMA_API, json={
            "model": "gemma3:4b", "prompt": prompt, "stream": False, "options": {"temperature": 0.2, "seed": 42}
        }, timeout=8).json()
        directive = resp.get("response", "").strip()
        
        agent_dir = AGENT_REGISTRY.get(agent_id, {}).get("dir")
        if agent_dir:
            eco_path = BASE_DIR / agent_dir / "memory" / "EVOLUTION.md"
            rules = []
            if eco_path.exists():
                rules = [line.strip() for line in eco_path.read_text(encoding='utf-8').split('\n') if line.strip()]
            
            rules.append(directive)
            if len(rules) > 5: rules = rules[-5:] # 保留最近 5 條黃金守則
                
            eco_path.write_text('\n'.join(rules), encoding='utf-8')
            log(f"🧬 [{agent_id}] 進化守則已寫入：{directive}")
    except Exception as e:
        log(f"⚠️ 進化分析異常: {e}")

def get_evolution_context(agent_id):
    agent_dir = AGENT_REGISTRY.get(agent_id, {}).get("dir")
    if agent_dir:
        eco_path = BASE_DIR / agent_dir / "memory" / "EVOLUTION.md"
        if eco_path.exists():
            content = eco_path.read_text(encoding='utf-8').strip()
            if content:
                return f"\n\n【自我進化守則 (絕對遵守)】\n{content}\n"
    return ""

def brain_worker():
    """🧠 大腦執行員：Phase 3 人格邏輯分離架構"""
    harness = Harness(BASE_DIR)
    audit = AuditLogger(BASE_DIR / "Shared_Vault" / "audit_log.jsonl")
    
    while True:
        task = task_queue.get()
        task_id, content = task['id'], task['content']
        agent_id = task.get('agent_id', 'unknown')
        agent_name = AGENT_REGISTRY.get(agent_id, {}).get('name', '未知代理')
        kanban_task_id = task.get('kanban_task_id')  # 若由 chat() 自動建立，則帶有此 ID
        
        # 🔑 智慧分流：判斷是否需要備份工作區
        is_write_task = harness.needs_checkpoint(content)
        mode_label = "寫入模式 🛡️" if is_write_task else "唯讀模式 ⚡"
        log(f"🧠 [{agent_name}] {mode_label} | {content[:20]}...")
        
        try:
            # L6: Shield 防禦掃描
            shield = Shield(BASE_DIR)
            safe, reason = shield.scan(content)
            if not safe:
                task_results[task_id] = f"🛡️ [Shield Defense] {reason}"
                task_queue.task_done()
                continue

            # L1: Checkpoint
            if is_write_task: harness.create_checkpoint(task_id)
            
            # Mem0 Context Injection + EVOLUTION.md + LTM
            memory_ctx = MM.build_memory_context(agent_id, content)
            if memory_ctx:
                log(f"🧠 LTM 記憶注入: {memory_ctx[:60]}...")
                
            session_context = MM.get_conversation_context(agent_id, max_history=10)
            evo_context = get_evolution_context(agent_id)
            
            # 🧪 上下文蒸餾：過濾聊天雜訊，轉化為精簡的技術狀態報告
            # 只在 session_context 有實質內容時才蒸餾（避免無謂 LLM 呼叫）
            if session_context and len(session_context) > 200:
                session_context = cerebellum_distill_context(session_context, content)
            
            prefix = ""
            if evo_context: prefix += evo_context + "\n"
            if memory_ctx: prefix += memory_ctx + "\n"
            if session_context: prefix += session_context + "\n"
            
            # Phase 6: Explicit Handoff Instruction
            handoff_instruction = (
                "\n\n【特權指令：人機協同交接 (Explicit Handoff)】\n"
                "若你遇到以下情況：\n"
                "1. 資訊極度不足，完全無法猜測老闆的意圖。\n"
                "2. 你的操作具有高風險（如：刪除重要資料庫檔案、關閉核心服務等），需要老闆的人工授權。\n"
                "請你**停止所有操作**，並在你的最終回覆中明確寫出以下字串：\n"
                "`HANDOFF_TO_HUMAN: [請在這裡寫下你需要老闆確認的問題或需要的資訊]`\n"
                "系統會自動把任務暫停並通知老闆。\n\n"
            )
            
            full_content = prefix + handoff_instruction + content
            
            # Phase 3: 直送原始問題給大腦 (OpenClaw)，不注入人格
            # 這樣 OpenClaw 可以專注於邏輯與工具使用
            oc_path = shutil.which("openclaw")
            if not oc_path:
                task_results[task_id] = "🚨 Error: OpenClaw executable not found in PATH."
                task_queue.task_done()
                continue
                
            MAX_RETRIES = 3
            final_raw_answer = ""
            success = True
            
            for attempt in range(MAX_RETRIES):
                # ✅ 使用 List 式參數傳遞，不使用 shell=True
                # 這樣可以避免訊息中含有引號、換行或特殊字元時造成的 shell 斷句錯誤
                cmd_args = [oc_path, "agent", "--agent", "main", "--no-color", "--message", full_content]
                if attempt > 0:
                    log(f"🧠 [OpenClaw] Self-Correction Round {attempt+1}/{MAX_RETRIES}...")
                else:
                    log(f"🛠️ [OpenClaw Debug] Running: {oc_path} agent --agent main --no-color --message <content_len={len(full_content)}>")
                
                process = subprocess.run(
                    cmd_args,
                    capture_output=True, text=True, encoding='utf-8', timeout=280
                )
                raw_answer = (process.stdout or "").strip()
                if not raw_answer: raw_answer = (process.stderr or "").strip()
                final_raw_answer = raw_answer
                
                if not is_write_task:
                    break
                    
                # L5: Validate
                success, error_msg = harness.validate()
                if success:
                    break
                
                log(f"⚠️ 第 {attempt + 1} 次驗證失敗。錯誤:\n{error_msg}")
                
                # ------ Cerebellum Hotfix Branch ------
                hotfix_success = False
                import re
                
                # Check for Syntax, Runtime, or Timeout errors in the specific file
                error_type = ""
                error_file = ""
                
                syntax_match = re.search(r"Syntax error in (.*?):", error_msg)
                runtime_match = re.search(r"Runtime error in (.*?) \(Exit code.*?\):", error_msg)
                timeout_match = re.search(r"Timeout error in (.*?):", error_msg)
                
                if syntax_match:
                    error_type = "語法錯誤 (Syntax Error)"
                    error_file = syntax_match.group(1).strip()
                elif runtime_match:
                    error_type = "執行期錯誤 (Runtime Error)"
                    error_file = runtime_match.group(1).strip()
                elif timeout_match:
                    error_type = "執行逾時 (Timeout/Infinite Loop)"
                    error_file = timeout_match.group(1).strip()

                if error_file:
                    file_path = list(harness.workspace.glob(f"**/{error_file}"))
                    if file_path:
                        target_file = file_path[0]
                        try:
                            with open(target_file, "r", encoding="utf-8") as f:
                                original_code = f.read()
                            
                            log(f"🧠 小腦 (Cerebellum) 嘗試進行 {error_file} {error_type} Hotfix...")
                            hotfix_prompt = (
                                f"你是一個專門修復 Python 程式錯誤的高級助手。以下程式碼執行發生了 {error_type}：\n"
                                f"```python\n{original_code}\n```\n"
                                f"系統拋出的錯誤訊息 (Truth Resistance)：\n{error_msg}\n"
                                f"請根據錯誤訊息修復這個 Bug。如果缺少 import，請補上；如果是邏輯錯誤，請修改邏輯。\n"
                                f"「只」回傳修復後的完整 Python 程式碼，絕對不要包含任何 Markdown 標籤 (例如 ```python) 或其他解釋。"
                            )
                            import requests
                            OLLAMA_API = "http://127.0.0.1:11434/api/generate"
                            resp = ollama_post(OLLAMA_API, json={
                                "model": "gemma3:4b",
                                "prompt": hotfix_prompt,
                                "stream": False,
                                "options": {"temperature": 0.1}
                            }, timeout=60).json()
                            fixed_code = resp.get("response", "").strip()
                            fixed_code = re.sub(r"^```python\s*|\n```$", "", fixed_code).strip()
                            
                            if fixed_code:
                                with open(target_file, "w", encoding="utf-8") as f:
                                    f.write(fixed_code)
                                
                                h_success, h_error_msg = harness.validate()
                                if h_success:
                                    log(f"✅ 小腦 Hotfix 成功！免除大腦重構 ({error_type})。")
                                    success = True
                                    hotfix_success = True
                                    final_raw_answer += f"\n\n[系統附註: 過程中有 {error_type}，已由小腦自動追蹤 Truth Resistance 並完成修復: {error_file}]"
                                else:
                                    log("❌ 小腦 Hotfix 依然失敗，交回大腦處理。")
                        except Exception as e:
                            log(f"⚠️ 小腦 Hotfix 異常: {e}")
                
                if hotfix_success:
                    break
                
                # ------ Brain Replan Branch ------
                harness.rollback(task_id)
                log("⚠️ 啟動 Brain Replan (大腦重新規劃)...")
                threading.Thread(target=generate_evolution_directive, args=(agent_id, content, error_msg)).start()
                
                full_content = (
                    f"你上一次的實作失敗了。系統 Linter/編譯器 回報了以下錯誤：\n"
                    f"```\n{error_msg}\n```\n"
                    f"請仔細分析這個錯誤，確保語意與縮排正確，並嘗試使用不同的方法修正它。\n\n"
                    f"【原始任務】\n{content}"
                )
            
            raw_answer = final_raw_answer
            
            # Phase 6: Explicit Handoff Detection
            if "HANDOFF_TO_HUMAN:" in raw_answer:
                handoff_msg = raw_answer.split("HANDOFF_TO_HUMAN:")[1].strip()
                log(f"⏸️ [Handoff] Agent 觸發人機交接: {handoff_msg[:50]}")
                
                if kanban_task_id:
                    KM.update_task(kanban_task_id, {
                        "status": "waiting_for_user",
                        "logs": f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⏸️ 任務暫停等待指示\n原因: {handoff_msg}"
                    })
                
                final_answer = cerebellum_style_transfer(
                    f"[Agent 需要您的協助]\n老闆，我在執行這個任務時遇到了顧慮，想先跟您確認：\n{handoff_msg}", 
                    agent_id
                )
                task_results[task_id] = final_answer
                task_queue.task_done()
                continue
            
            if is_write_task and not success:
                raw_answer = f"⚠️ [經過 {MAX_RETRIES} 次驗證皆失敗] 已自動回滾狀態。最後一次錯誤：\n{error_msg}\n\n{raw_answer}"
            
            # Phase 3: 小腦風格轉移 (Logic -> Persona)
            final_answer = cerebellum_style_transfer(raw_answer, agent_id)
            
            # L3/L4: 稽核記錄
            audit.append(task_id, content, final_answer, success, agent_id=agent_id)
            
            # 🗂️ 自動更新 Kanban 看板（若此任務由 chat() 自動建立）
            if kanban_task_id:
                log_snippet = final_answer[:300] + "..." if len(final_answer) > 300 else final_answer
                KM.update_task(kanban_task_id, {
                    "status": "done",
                    "logs": f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ 執行完成\n{log_snippet}"
                })
                log(f"🗂️ Kanban 已更新: {kanban_task_id[:8]}... → done")
                notify_kanban_clients()
            
            # Mem0 Append Chats & Compress
            MM.append_chat(agent_id, "user", content)
            MM.append_chat(agent_id, "assistant", final_answer)
            threading.Thread(target=MM._compress_old_chats, args=(agent_id,)).start()
            
            threading.Thread(target=update_cache, args=(content, final_answer)).start()
            task_results[task_id] = final_answer
        except Exception as e:
            err_msg = f"🚨 大腦異常: {str(e)}"
            # 🗂️ 任務異常時也更新 Kanban
            if kanban_task_id:
                KM.update_task(kanban_task_id, {
                    "status": "done",
                    "logs": f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ❌ 執行失敗\n{err_msg}"
                })
            task_results[task_id] = err_msg
        
        task_queue.task_done()

threading.Thread(target=brain_worker, daemon=True).start()

@app.route('/v1/harness/night-mode', methods=['POST'])
def trigger_night_mode():
    """手動或定時觸發夜間蒸餾"""
    result = perform_night_distillation()
    return jsonify({"status": "success", "message": result})

@app.route('/v1/harness/reload-agents', methods=['POST'])
def reload_agents():
    """🔥 熱重利代理人設定 (無需重啟 Bridge)"""
    load_agent_registry()
    # 清除人格快取，確保新設定生效
    PE.invalidate()
    return jsonify({"status": "success", "message": f"Agents reloaded. Total: {len(AGENT_REGISTRY)}", "agents": list(AGENT_REGISTRY.keys())})

@app.route('/v1/team/dispatch', methods=['POST'])
def api_dispatch_task():
    """👮 多代理團隊調度接口"""
    data = request.json
    role = data.get("role")
    payload = data.get("payload")
    task_id = data.get("task_id", str(uuid.uuid4()))
    
    if not role or not payload:
        return jsonify({"error": "Missing role or payload"}), 400
        
    result = Dispatcher.dispatch(task_id, role, payload)
    return jsonify({"task_id": task_id, "role": role, "result": result})

@app.route('/v1/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """查詢任務狀態"""
    if task_id in task_results:
        return jsonify({"status": "completed", "result": task_results.pop(task_id)})
    return jsonify({"status": "processing"})

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    global last_activity_time
    try:
        last_activity_time = time.time()  # 更新最後活動時間 (Dimension 2)
        data = request.json
        user_input = data['messages'][-1]['content']
        agent_id = data.get('agent_id', 'unknown')
        origin = data.get('origin', '')  # 🔒 穿透標記：'kanban_poller' 表示來自看板說調器，防止建立重複任務
        agent_name = AGENT_REGISTRY.get(agent_id, {}).get('name', '未知')
        log(f"📨 收到來自 [{agent_name}] 的請求{' (看板說調器)' if origin == 'kanban_poller' else ''}")
        
        # 0. 特殊指令攔截 (Dispatcher)
        if user_input.startswith("dispatch:"):
            # 格式: dispatch:role:instruction
            try:
                _, role, payload = user_input.split(":", 2)
                task_id = f"task_{int(time.time())}"
                result = Dispatcher.dispatch(task_id, role.strip(), payload.strip())
                return jsonify({"choices": [{"message": {"content": f"👮 [Dispatcher Result]\n{result}"}}]})
            except ValueError:
                return jsonify({"choices": [{"message": {"content": "❌ 格式錯誤。請使用: dispatch:role:instruction"}}]})



        # 1. 小腦快取檢查 (同步)
        cached = cerebellum_semantic_check(user_input)
        if cached and cached != "OLLAMA_BUSY": 
            return jsonify({"choices": [{"message": {"content": f"[Ariel 智慧快取]\n{cached}"}}]})
        
        ollama_busy = (cached == "OLLAMA_BUSY")  # 🚨 Ollama 忙磁標記，將跳過 FastTrack 節省 60s
        if ollama_busy:
            log("⚡ Ollama 忙磁，跳過 FastTrack 直接入列大腦")
            
        # 1.5. 脊髓反射 (最速回應 Phase) - 針對「今天日期」等極簡問題，直接攔截不進 LLM
        reflex_ans = spinal_chord_reflex(user_input, agent_id)
        if reflex_ans:
            log(f"⚡ 脊髓反射命中: {reflex_ans}")
            return jsonify({"choices": [{"message": {"content": reflex_ans}}]})
        
        # 2. 長期記憶檢索 (Phase 14) 已移至 brain_worker，避免阻塞 HTTP 回應與小腦快車道。

        # 為了避免小腦快車道 (Fast Track) 因為上千字的長期記憶而引發 Ollama 150秒算力瓶頸，
        # 我們只傳遞原生的 `user_input`，讓它專注判定意圖。真正的歷史回憶由大腦 OpenClaw 負責。

        # 3. 小腦快車道 (Fast Track) — 若 Ollama 忙碌則跳過，節省 60s 等待
        intent_type, fast_ans = (None, None)
        if not ollama_busy:
            intent_type, fast_ans = cerebellum_fast_track_check(user_input, agent_id)
        
        if intent_type == "SIMPLE":
            # 閒聲/小咋 — 不進看板，直接回傳
            log(f"⚡ Fast Track [SIMPLE]: {fast_ans[:20]}...")
            MM.append_chat(agent_id, "user", user_input)
            MM.append_chat(agent_id, "assistant", fast_ans)
            threading.Thread(target=MM._compress_old_chats, args=(agent_id,)).start()
            return jsonify({"choices": [{"message": {"content": fast_ans}}]})
        
        if intent_type in ("SEARCH", "SKILL"):
            # 搜尋/技能 — 建立 Kanban 卡片
            kanban_entry = KM.add_task(
                title=user_input[:80] + ('...' if len(user_input) > 80 else ''),
                agent_id=agent_id,
                status="doing",
                priority="low"
            )
            log(f"🗂️ Kanban [{intent_type}] 建立: {user_input[:30]}...")
            # 立即標記為 done（搜尋已執行完成）
            result_snippet = fast_ans[:300] + '...' if len(fast_ans) > 300 else fast_ans
            KM.update_task(kanban_entry['id'], {
                "status": "done",
                "logs": f"[小腦 {intent_type}] {result_snippet}"
            })
            log(f"⚡ Fast Track [{intent_type}] 完成: {fast_ans[:20]}...")
            notify_kanban_clients()
            MM.append_chat(agent_id, "user", user_input)
            MM.append_chat(agent_id, "assistant", fast_ans)
            threading.Thread(target=MM._compress_old_chats, args=(agent_id,)).start()
            return jsonify({"choices": [{"message": {"content": fast_ans}}]})
        
        if intent_type is not None:
            # 其他非空巧情況也直接回傳
            return jsonify({"choices": [{"message": {"content": fast_ans}}]})
        
        # 3. 自動建立 Kanban 任務（讓看板即時顯示執行中的 Job）
        # ❗ 如果來源是看板說調器，跳過建立新看板任務，防止無限迴圈
        kanban_task_id = None
        if origin != 'kanban_poller':
            agent_name_label = AGENT_REGISTRY.get(agent_id, {}).get('name', agent_id)
            kanban_entry = KM.add_task(
                title=user_input[:80] + ('...' if len(user_input) > 80 else ''),
                agent_id=agent_id,
                status="doing",
                priority="medium"
            )
            kanban_task_id = kanban_entry['id']
            log(f"🗂️ Kanban Job 建立: [{agent_name_label}] {user_input[:30]}...")
            notify_kanban_clients()
        
        # 4. 建立任務 ID 並入列（帶入 kanban_task_id 以便完成後回寫）
        tid = str(uuid.uuid4())
        task_queue.put({
            'id': tid,
            'content': user_input,
            'agent_id': agent_id,
            'kanban_task_id': kanban_task_id  # 連結 Kanban 任務 (None if origin=kanban_poller)
        })
        
        # 5. 立即回傳 Accepted (202) 與 Task ID
        # ❗ 重要：這裡必須立即回傳，不應再往下執行任何邏輯，否則會造成同步/非同步雙重執行
        log(f"✅ 任務 {tid} 已入列 (腦部處理中)")
        return jsonify({"task_id": tid, "status": "queued"}), 202

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Phase 10: Kanban API & SSE Real-time Sync (Phase 6) ---

kanban_clients = []

def notify_kanban_clients():
    """發送更新訊號給所有已連線的 Kanban SSE 客戶端"""
    dead_clients = []
    for q in kanban_clients:
        try:
            q.put_nowait({"type": "update", "data": KM.get_all()})
        except queue.Full:
            dead_clients.append(q)
    for q in dead_clients:
        kanban_clients.remove(q)

@app.route('/v1/kanban/stream')
def kanban_stream():
    """Server-Sent Events (SSE) Endpoint for real-time Kanban updates"""
    def event_stream():
        q = queue.Queue(maxsize=10)
        kanban_clients.append(q)
        try:
            # 首次連線時立即遞送完整狀態
            yield f"data: {json.dumps(KM.get_all())}\n\n"
            while True:
                message = q.get(timeout=30)
                yield f"data: {json.dumps(message['data'])}\n\n"
        except queue.Empty:
            # 保持連線的心跳封包 (Keep-alive)
            yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            if q in kanban_clients:
                kanban_clients.remove(q)

    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/kanban')
def kanban_ui():
    """Serve Kanban HTML"""
    return app.send_static_file('kanban.html')

@app.route('/v1/kanban/tasks', methods=['GET'])
def get_kanban_tasks():
    return jsonify(KM.get_all())

@app.route('/v1/kanban/tasks', methods=['POST'])
def add_kanban_task():
    try:
        data = request.json
        title = data.get('title', 'Unknown Task')
        
        # Phase 11: AI Analysis
        analysis = analyze_task_intent(title)
        
        task = KM.add_task(
            title=title,
            agent_id=data.get('agent_id', 'agent1'),
            status=data.get('status', 'todo'),
            priority=analysis.get('priority', 'medium')
        )
        # Add brain tag explicitly (KM.add_task puts extra kwargs into task dict? No, let's update it)
        # Wait, KM.add_task doesn't accept extra args. I should update KM.add_task or update the task immediately.
        # Let's update KM.add_task signature in next step or just patch it here.
        # Actually KM.update_task is cleaner or just modify KM.add_task now?
        # I'll update KM.add_task signature in previous tool call? No, existing code:
        # def add_task(self, title, agent_id, status="todo", priority="medium"): ...
        # It creates a dict. I can just update the task dict in memory and save.
        
        # Re-read KM.add_task:
        # task = { ... "priority": priority ... }
        # data["tasks"].append(task); self._save(data); return task
        
        # So I need to patch the brain type in.
        KM.update_task(task['id'], {"brain": analysis.get("brain", "cerebellum")})
        task['brain'] = analysis.get("brain", "cerebellum")
        notify_kanban_clients()
        return jsonify(task)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/kanban/tasks/<tid>', methods=['PATCH'])
def update_kanban_task(tid):
    try:
        updates = request.json
        # Protect ID from being changed
        updates.pop('id', None)
        task = KM.update_task(tid, updates)
        if task: 
            notify_kanban_clients()
            return jsonify(task)
        return jsonify({"error": "Task not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/kanban/tasks/<tid>', methods=['DELETE'])
def delete_kanban_task(tid):
    try:
        if KM.delete_task(tid):
            return jsonify({"status": "deleted"})
        return jsonify({"error": "Task not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Phase 13: Skills API ---

@app.route('/v1/skills', methods=['GET'])
def list_skills():
    """列出已安裝技能與目錄"""
    return jsonify({
        "installed": SM.list_installed(),
        "catalog": SM.list_catalog()
    })

@app.route('/v1/skills/search', methods=['POST'])
def search_skills():
    """搜尋可用技能"""
    query = request.json.get('query', '')
    results = SM.search_skill_online(query)
    return jsonify(results)

@app.route('/v1/skills/install', methods=['POST'])
def install_skill_api():
    """手動安裝技能"""
    skill_info = request.json
    success = SM.install_skill(skill_info)
    return jsonify({"status": "installed" if success else "failed"})

@app.route('/v1/skills/<name>', methods=['DELETE'])
def remove_skill(name):
    """移除技能"""
    success = SM.remove_skill(name)
    return jsonify({"status": "removed" if success else "not_found"})

# ----------------------------

if __name__ == '__main__':
    log(f"ArielOS 智慧總部 v1.1 啟動成功 | 路徑鎖定: {BASE_DIR}")
    log(f"🧠 小腦模型配置 | 主要: {CEREBELLUM_MODEL} | 備用 (Fallback): {CEREBELLUM_FALLBACK_MODEL}")
    log(f"🤖 Dispatcher 模型: {DISPATCHER_MODEL}")
    # 啟動自動排程執行緒
    threading.Thread(target=scheduler_worker, daemon=True).start()
    
    # 🛡️ Stability Evolution: 從 Flask Dev Server 升級為 Waitress WSGI (支援高併發與防斷線)
    from waitress import serve
    log("🚀 啟動 Waitress 生產級伺服器 (Port 28888)...")
    serve(app, host='0.0.0.0', port=28888, threads=16)
