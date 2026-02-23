# -*- coding: utf-8 -*-
"""
memory_manager.py — ArielOS 沙盒記憶與長期記憶 (LTM) 管理器 (SQLite 強化版)

優化重點：
1. 使用 SQLite 代替 JSON，大幅提升大數據量下的讀寫效能。
2. 建立全文檢索與關鍵字索引。
3. 加入 In-memory 快取機制，相同查詢秒回。
"""

import sqlite3
import datetime
import json
import threading
import requests
from pathlib import Path
from functools import lru_cache

# 模型配置 (與 ariel_bridge.py 同步)
_CEREBELLUM_MODEL = "gemma3:4b-it-q4_K_M"
_CEREBELLUM_FALLBACK = "gemma3:4b"
_OLLAMA_API = "http://127.0.0.1:11434/api/generate"


def _cerebellum_call(prompt: str, temperature: float = 0.1, timeout: int = 120,
                    num_ctx: int = 3072, num_predict: int = 512) -> str:
    """🧠 MemoryManager 內醒用小腦介面（含自動模型降級）"""
    payload = {"prompt": prompt, "stream": False,
               "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict}}
    try:
        resp = requests.post(_OLLAMA_API, json={**payload, "model": _CEREBELLUM_MODEL}, timeout=timeout)
        return resp.json().get('response', '').strip()
    except Exception:
        pass  # 降級至備用模型
    try:
        resp = requests.post(_OLLAMA_API, json={**payload, "model": _CEREBELLUM_FALLBACK}, timeout=timeout)
        return resp.json().get('response', '').strip()
    except Exception as e:
        print(f"⚠️ [MemoryManager] 小腦呼叫很役失敗: {e}")
        return ""


class MemoryManager:
    """代理人長期記憶管理器 (SQLite Optimized)"""

    MAX_FACTS_PER_AGENT = 5000  # SQLite 支撐能力較強，上限提升
    CACHE_SIZE = 128           # 搜尋結果快取大小

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / "Shared_Vault" / "Memory" / "ariel_ltm.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self):
        """取得資料庫連線"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化資料庫表結構"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # 主事實表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS facts (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    timestamp TEXT,
                    type TEXT,
                    content TEXT,
                    keywords TEXT,
                    recall_count INTEGER DEFAULT 0
                )
            ''')
            
            # 對話歷史表 (Raw Messages) - Mem0 Style
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT
                )
            ''')
            
            # 會話摘要表 (Session Summaries) - Mem0 Style
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    summary TEXT,
                    timestamp TEXT
                )
            ''')
            
            # 建立索引以加速查詢
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_id ON facts(agent_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_type ON facts(type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_agent ON chat_history(agent_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_summary_agent ON session_summaries(agent_id)')
            
            conn.commit()
            conn.close()

    # ── CRUD 操作 ─────────────────────────────────────────────────────────────

    def add_fact(self, agent_id: str, content: str, fact_type: str = "其他", keywords: list[str] | None = None) -> dict:
        """新增一筆長期記憶"""
        fact_id = f"{agent_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        ts = datetime.datetime.now().isoformat()
        kw_str = json.dumps(keywords or [])
        
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO facts (id, agent_id, timestamp, type, content, keywords)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (fact_id, agent_id, ts, fact_type, content, kw_str))
            
            # 每新增一筆就檢查上限並清理
            cursor.execute('''
                DELETE FROM facts 
                WHERE agent_id = ? AND id NOT IN (
                    SELECT id FROM facts WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?
                )
            ''', (agent_id, agent_id, self.MAX_FACTS_PER_AGENT))
            
            conn.commit()
            conn.close()
            
        # 清除相關快取
        self.retrieve_relevant.cache_clear()
        
        return {
            "id": fact_id,
            "agent_id": agent_id,
            "timestamp": ts,
            "type": fact_type,
            "content": content,
            "keywords": keywords or []
        }

    @lru_cache(maxsize=CACHE_SIZE)
    def retrieve_relevant(self, agent_id: str, query: str, top_k: int = 5) -> list[dict]:
        """
        關鍵字檢索：從 SQLite 記憶中找出最相關的內容。
        利用 LRU Cache 進行效能優化。
        """
        query_words = [w.lower() for w in query.split() if len(w) > 1]
        if not query_words:
            # 若無特定關鍵字，回傳最近的記憶
            return self._get_recent(agent_id, top_k)

        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 簡單的 LIKE 搜尋與權重排序
        # 實作說明：優先尋找關鍵字欄位命中，其次是內容欄位命中
        rows = conn.execute('SELECT * FROM facts WHERE agent_id = ?', (agent_id,)).fetchall()
        
        scored = []
        for row in rows:
            score = 0
            content = row['content'].lower()
            keywords = json.loads(row['keywords'])
            
            # 關鍵字完全命中：權重最高
            for qw in query_words:
                if any(qw in kw.lower() for kw in keywords):
                    score += 5
                if qw in content:
                    score += 2
            
            # 基礎權重：召回次數與時間衰減
            score += row['recall_count'] * 0.2
            
            if score > 0:
                scored.append((score, dict(row)))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [item for score, item in scored[:top_k]]
        
        # 異步更新召回次數（簡單實作，直接在結束前更新）
        if results:
            with self._lock:
                u_conn = self._get_conn()
                ids = [f['id'] for f in results]
                u_conn.executemany('UPDATE facts SET recall_count = recall_count + 1 WHERE id = ?', [(rid,) for rid in ids])
                u_conn.commit()
                u_conn.close()
                
        conn.close()
        return results

    def _get_recent(self, agent_id: str, limit: int) -> list[dict]:
        """私有方法：取得最近的記憶"""
        conn = self._get_conn()
        rows = conn.execute('''
            SELECT * FROM facts WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?
        ''', (agent_id, limit)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def delete_fact(self, agent_id: str, fact_id: str) -> bool:
        """刪除記憶"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM facts WHERE id = ? AND agent_id = ?', (fact_id, agent_id))
            changed = conn.total_changes > 0
            conn.commit()
            conn.close()
        self.retrieve_relevant.cache_clear()
        return changed

    # ── 介面方法 ─────────────────────────────────────────────────────────────

    def build_memory_context(self, agent_id: str, query: str) -> str:
        """為 Prompt 注入相關記憶上下文"""
        relevant = self.retrieve_relevant(agent_id, query, top_k=5)
        if not relevant:
            return ""
        
        lines = [f"- [{r['type']}] {r['content']}" for r in relevant]
        block = "\n".join(lines)
        return f"[老闆長期記憶內容]\n{block}\n"

    def get_summary_for_soul(self, agent_id: str, max_items: int = 10) -> str:
        """為 SOUL.md 生成摘要格式"""
        recent = self._get_recent(agent_id, max_items)
        if not recent:
            return "（尚未有長期記憶記錄）"
        
        lines = [f"- [{r['timestamp'][:10]}][{r['type']}] {r['content']}" for r in recent]
        return "\n".join(lines)

    def get_all_facts(self, agent_id: str) -> list[dict]:
        """取得該代理人所有事實紀錄"""
        conn = self._get_conn()
        rows = conn.execute('SELECT * FROM facts WHERE agent_id = ? ORDER BY timestamp DESC', (agent_id,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ── Mem0 Style Context 管理 ───────────────────────────────────────────────

    def append_chat(self, agent_id: str, role: str, content: str):
        """將新對話加入歷史記錄中，此為 Session Checkpoint 的基礎"""
        ts = datetime.datetime.now().isoformat()
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO chat_history (agent_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (agent_id, role, content, ts))
            conn.commit()
            conn.close()

    def get_conversation_context(self, agent_id: str, max_history: int = 10) -> str:
        """
        組裝 Prompt 所需的上下文：
        格式為 [Session Summary] + [Recent Raw Messages]
        """
        conn = self._get_conn()
        
        # 1. 取得最新的會話摘要
        summary_row = conn.execute('''
            SELECT summary FROM session_summaries 
            WHERE agent_id = ? ORDER BY timestamp DESC LIMIT 1
        ''', (agent_id,)).fetchone()
        
        session_summary_text = ""
        if summary_row and summary_row['summary']:
            session_summary_text = f"【近期對話摘要】\n{summary_row['summary']}\n\n"

        # 2. 取得最近的對話歷史 (最後 N 筆)
        history_rows = conn.execute('''
            SELECT role, content FROM chat_history 
            WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?
        ''', (agent_id, max_history)).fetchall()
        conn.close()

        # history_rows 是 DESC 排序 (最新在最前面)，但給 LLM 閱讀通常需要順著時間 ( oldest -> newest )
        history_rows = history_rows[::-1]

        recent_chats_text = ""
        if history_rows:
            recent_chats_text = "【近期對話細節】\n"
            for row in history_rows:
                r_label = "老闆" if row['role'] == "user" else "你"
                recent_chats_text += f"{r_label}: {row['content']}\n"
            recent_chats_text += "\n"

        return session_summary_text + recent_chats_text

    def _compress_old_chats(self, agent_id: str, threshold: int = 15, keep: int = 5):
        """
        [Mem0 核心機制]
        當歷史紀錄超過 `threshold` 時，將舊的紀錄抓出來加上現有的 summary，
        交給 LLM 壓縮成新的 session_summary，然後刪除這些舊紀錄。
        藉此保持 Prompt 令牌數量在健康範圍，解決金魚腦問題。
        """
        conn = self._get_conn()
        
        # 檢查對話數量
        count_row = conn.execute('SELECT COUNT(*) as c FROM chat_history WHERE agent_id = ?', (agent_id,)).fetchone()
        if not count_row or count_row['c'] <= threshold:
            conn.close()
            return
            
        # 抓取「舊的」紀錄 (排除最近的 keep 筆)
        # SQLite 的 LIMIT/OFFSET 可以達成：取得全部但不包含最晚的 keep 筆
        old_chats = conn.execute('''
            SELECT id, role, content FROM chat_history
            WHERE agent_id = ?
            ORDER BY timestamp ASC
            LIMIT -1 OFFSET 0 -- 我們會手動在 Python 內計算以策安全
        ''', (agent_id,)).fetchall()
        
        if len(old_chats) <= keep:
            conn.close()
            return
            
        # 要壓縮的是最早的幾筆
        to_compress = old_chats[:-keep]
        ids_to_delete = [row['id'] for row in to_compress]
        
        old_dialogue_text = ""
        for row in to_compress:
            r_label = "老闆" if row['role'] == "user" else "你"
            old_dialogue_text += f"{r_label}: {row['content']}\n"
            
        # 抓出現存的 summary
        summary_row = conn.execute('''
            SELECT summary FROM session_summaries 
            WHERE agent_id = ? ORDER BY timestamp DESC LIMIT 1
        ''', (agent_id,)).fetchone()
        current_summary = summary_row['summary'] if summary_row else ""
        conn.close()
        
        # 呼叫 LLM 進行壓縮
        prompt = (
            "你是一個對話記憶壓縮專家。請將目前的對話摘要與最新的一段舊對話記錄合併，"
            "產生一段連貫、高密度的上下文摘要。摘要必須保留所有的關鍵實體、待详事項與使用者的意圖。\n"
            "請「直接」輸出新的摘要，不要包含任何開場白或解釋。\n\n"
        )
        if current_summary:
            prompt += f"【目前的記憶摘要】\n{current_summary}\n\n"
        prompt += f"【要合併的舊對話細節】\n{old_dialogue_text}"
        
        try:
            new_summary = _cerebellum_call(
                prompt=prompt,
                temperature=0.1,
                timeout=300,
                num_ctx=3072,
                num_predict=512
            )
            
            if new_summary:
                ts = datetime.datetime.now().isoformat()
                with self._lock:
                    w_conn = self._get_conn()
                    # 寫入新摘要
                    w_conn.execute('''
                        INSERT INTO session_summaries (agent_id, summary, timestamp)
                        VALUES (?, ?, ?)
                    ''', (agent_id, new_summary, ts))
                    # 刪除已壓縮的對話
                    w_conn.executemany('DELETE FROM chat_history WHERE id = ?', [(rid,) for rid in ids_to_delete])
                    w_conn.commit()
                    w_conn.close()
                print(f"🧠 [MemoryManager] 成功將 {len(to_compress)} 筆紀錄壓縮入會話摘要中。")
        except Exception as e:
            print(f"⚠️ [MemoryManager] 會話壓縮失敗: {e}")
