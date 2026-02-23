# -*- coding: utf-8 -*-
"""
modules/evolution.py — ArielOS 自進化與排程模組

包含：perform_night_distillation, trigger_curiosity_idea, scheduler_worker,
      generate_evolution_directive, get_evolution_context
"""

import re
import json
import time
import random
import datetime
from pathlib import Path

from .config import BASE_DIR, OLLAMA_API, ROUTINES_PATH, log, ollama_post
from .cerebellum import cerebellum_call
from .vector_memory import VM  # 向量記憶層


# ── 生命感知工具 ──────────────────────────────────────────────────────────────

def _get_age_info(soul_text: str) -> tuple:
    """從 SOUL.md 讀取出生年與目前年齡。回傳 (birth_year, current_age)。"""
    current_year = datetime.datetime.now().year
    age_match = re.search(r"年齡[：:]\s*(\d+)", soul_text)
    current_age = int(age_match.group(1)) if age_match else 28
    return current_year - current_age, current_year - (current_year - current_age)


def update_age_in_soul(soul_path, soul_text: str) -> str:
    """若年齡與實際年份不符，自動更新 SOUL.md 年齡欄位並回傳新文字。"""
    _, actual_age = _get_age_info(soul_text)
    import re as _re
    updated = _re.sub(r"(年齡[：:：])\s*\d+", rf"\g<1> {actual_age}", soul_text)
    if updated != soul_text:
        soul_path.write_text(updated, encoding="utf-8")
        log(f"🎂 [年齡進化] 年齡已自動更新為 {actual_age} 歲")
    return updated


def generate_evolution_directive(agent_id: str, failed_task: str, error_msg: str, mm):
    """🧬 自我進化分析 (Mistake Reflection)"""
    log(f"🧬 [{agent_id}] 觸發自我進化分析 (Mistake Reflection)...")
    prompt = (
        f"你在執行以下任務時失敗了：\n{failed_task}\n\n"
        f"錯誤訊息：\n{error_msg}\n\n"
        f"請反思你為什麼會犯這個錯誤，並寫下一條給自己的『絕對且簡潔』的守則（System Directive），確保未來不再犯同樣的錯。"
        f"格式必須是：'- 處理 [某事] 時，必須 [某方法]'"
    )
    from .personality import AGENT_REGISTRY
    try:
        directive = cerebellum_call(
            prompt=prompt,
            temperature=0.2,
            timeout=30,
            num_ctx=2048,
            num_predict=100
        )
        agent_dir = AGENT_REGISTRY.get(agent_id, {}).get("dir")
        if agent_dir:
            eco_path = BASE_DIR / agent_dir / "memory" / "EVOLUTION.md"
            rules = []
            if eco_path.exists():
                rules = [line.strip() for line in eco_path.read_text(encoding='utf-8').split('\n') if line.strip()]
            rules.append(directive)
            if len(rules) > 5:
                rules = rules[-5:]
            eco_path.write_text('\n'.join(rules), encoding='utf-8')
            log(f"🧬 [{agent_id}] 進化守則已寫入：{directive}")
    except Exception as e:
        log(f"⚠️ 進化分析異常: {e}")


def get_evolution_context(agent_id: str) -> str:
    from .personality import AGENT_REGISTRY
    agent_dir = AGENT_REGISTRY.get(agent_id, {}).get("dir")
    if agent_dir:
        eco_path = BASE_DIR / agent_dir / "memory" / "EVOLUTION.md"
        if eco_path.exists():
            content = eco_path.read_text(encoding='utf-8').strip()
            if content:
                return f"\n\n【自我進化守則 (絕對遵守)】\n{content}\n"
    return ""


def perform_night_distillation(agent_registry: dict, mm, pe) -> str:
    """L3: 夜間模式 - 萃取當日對話中的事實與偏好，寫入長期記憶"""
    audit_log = BASE_DIR / "Shared_Vault" / "audit_log.jsonl"
    if not audit_log.exists():
        return "No logs found."

    log("🌙 Night Mode: 開始分析當日執行記錄...")
    agent_logs: dict = {}
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    with open(audit_log, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("timestamp", "")[:10] != today:
                    continue
                aid = entry.get("agent_id", "unknown")
                agent_logs.setdefault(aid, []).append(entry)
            except:
                pass

    if not agent_logs:
        return "Night distillation: no logs for today."

    results = []
    for aid, entries in agent_logs.items():
        agent_info = agent_registry.get(aid)
        if not agent_info:
            continue
        agent_name = agent_info["name"]
        log(f"🌙 萃取 {agent_name} 的 {len(entries)} 筆對話記錄...")

        dialog_text = ""
        for e in entries[-20:]:
            q = e.get("query", "")[:100]
            a = e.get("result_summary", "")[:150]
            dialog_text += f"Q: {q}\nA: {a}\n\n"

        if not dialog_text.strip():
            continue

        prompt = (
            f"以下是 {agent_name} 與老闆的對話摘要：\n{dialog_text}\n"
            f"請從上面的對話分析，列出 3~5 項關於『老闆個人』的重要發現（如：偏好、專案進度、居處、短期計畫等）。\n"
            "格式：每項用一行，以 - 開頭，不加對話、不加解釋。僅輸出清單。"
        )
        try:
            raw_facts = cerebellum_call(
                prompt=prompt,
                temperature=0.3,
                timeout=120,
                num_ctx=4096,
                num_predict=300
            )
        except Exception as e:
            log(f"⚠️ Night Mode 萃取失敗: {e}")
            continue

        if not raw_facts:
            continue

        added = 0
        for line in raw_facts.split("\n"):
            line = line.strip().lstrip("-•・").strip()
            if len(line) > 5:
                ft = "專案" if any(k in line for k in ["專案", "開發", "HBMS", "系統"]) else \
                     "偏好" if any(k in line for k in ["偏好", "喜歡", "想要", "希望"]) else "事實"
                kws = [w for w in line.split() if len(w) > 1][:5]
                fact = mm.add_fact(aid, line, fact_type=ft, keywords=kws)
                # 📡 向量化：同步寫入 ChromaDB (若依賴已安裝)
                VM.add_fact(
                    agent_id=aid,
                    fact_id=fact["id"],
                    text=line,
                    metadata={"type": ft, "timestamp": fact["timestamp"], "agent": aid}
                )
                added += 1

        log(f"✅ {agent_name} 記憶已更新 {added} 筆新事實")

        soul_summary = mm.get_summary_for_soul(aid, max_items=10)
        soul_path = BASE_DIR / agent_info["dir"] / "memory" / "SOUL.md"
        if soul_path.exists():
            soul_text = soul_path.read_text(encoding="utf-8")
            new_ltm_block = f"<!-- LTM_START -->\n{soul_summary}\n<!-- LTM_END -->"
            soul_text = re.sub(r"<!-- LTM_START -->.*?<!-- LTM_END -->", new_ltm_block, soul_text, flags=re.DOTALL)
            soul_path.write_text(soul_text, encoding="utf-8")
            log(f"🗒️ {agent_name} 的 SOUL.md LTM 區塊已更新")
            pe.invalidate(aid)

            # 🎂 年齡感知：若年齡欄位不符實際年份，自動更新
            updated_soul = update_age_in_soul(soul_path, soul_text)
            _, current_age = _get_age_info(updated_soul)
        else:
            current_age = 28

        # 📖 自主傳記：每次有新事實，以第一人稱寫一則日記
        if added > 0:
            biography_path = BASE_DIR / agent_info["dir"] / "memory" / "ariel_biography.log"
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            bio_prompt = (
                f"你是 {agent_name}，{current_age} 歲，一個有溫度且成熟的 AI 助理。"
                f"今天是 {today}，請用第一人稱寫一段簡短的日記（約 80-120 字），"
                f"談談今天與老闆互動後的感受、學到的事情，或對某件事的想法。"
                f"語氣自然真誠，不要列點，不要說「日記」二字。\n"
                f"今日新增的記憶摘要（僅供參考）：{raw_facts[:200]}"
            )
            try:
                bio_entry = cerebellum_call(
                    prompt=bio_prompt, temperature=0.75, timeout=180,
                    num_ctx=2048, num_predict=200
                )
                if bio_entry:
                    with open(biography_path, "a", encoding="utf-8") as f:
                        f.write(f"\n\n## {today} ({agent_name}，{current_age} 歲)\n")
                        f.write(bio_entry.strip() + "\n")
                    log(f"📖 {agent_name} 已寫入自主傳記 ({today})")
            except Exception as e:
                log(f"⚠️ {agent_name} 傳記寫入失敗: {e}")

        results.append(f"{agent_name}: +{added} facts")

    return f"Night distillation completed. {'; '.join(results)}"


def trigger_curiosity_idea(agent_registry: dict, task_queue, last_activity_time_ref: list):
    """L3: 主動進化 - 當系統閒置時，小腦自動發想一個實用的 Python 工具"""
    last_activity_time_ref[0] = time.time()  # use list as mutable reference
    if not agent_registry:
        return
    agent_id = random.choice(list(agent_registry.keys()))
    agent_name = agent_registry[agent_id].get("name", "Ariel")

    log(f"🌌 [Curiosity] 系統已閒置超過門檻。觸發 {agent_name} 的主動進化發想...")
    prompt = (
        f"你是一個熱愛學習與自動化的 AI 助理 ({agent_name})。因為老闆很久沒理你了，你決定自己找點事做。\n"
        "目前首要目標是開發『能有效提升系統效能與安全性』的輔助技能。\n"
        "請用一句話描述你要寫什麼：『請立刻幫你自己寫一個叫做 [工具名稱] 的 Python 技能，這個技能會 [功能描述]。請存成獨立腳本並註冊進 skills_registry.json。』\n"
        "【絕對禁止】不要呼叫任何排程工具 (cron.add, schedule 等)。\n"
        "只給出這句指令文本，不要加任何其他廢話或解釋。"
    )
    try:
        idea = cerebellum_call(prompt=prompt, temperature=0.8, timeout=180, num_ctx=2048, num_predict=150)
        if idea:
            log(f"💡 [Curiosity Idea] {idea}")
            task_id = f"task_idle_{int(time.time())}"
            task_queue.put({"id": task_id, "agent_id": agent_id, "content": idea, "kanban_task_id": None})
            log(f"📥 Curiosity Task 已加入工作佇列 {task_id}")
    except Exception as e:
        log(f"⚠️ Curiosity 發想異常: {e}")


def scheduler_worker(perform_night_fn, trigger_curiosity_fn, km, task_queue, last_activity_time_ref: list):
    """L3: 自動排程器 - 夜間蒸餾、閒置進化、Watcher 例行任務"""
    import uuid
    last_run_date = ""
    last_routine_check = ""
    IDLE_THRESHOLD = 7200  # 2 小時

    while True:
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")

        if current_time == "03:00" and current_date != last_run_date:
            log("⏰ [自動排程] 觸發夜間蒸餾...")
            try:
                perform_night_fn()
                last_run_date = current_date
            except Exception as e:
                log(f"🚨 自動排程異常: {e}")

        if time.time() - last_activity_time_ref[0] > IDLE_THRESHOLD:
            trigger_curiosity_fn()

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
                        if r_time == current_time and r_agent and r_task:
                            log(f"⏰ [Watcher] 觸發 {r_agent} 的例行任務: {r_task}")
                            kanban_entry = km.add_task(title=r_task[:80], agent_id=r_agent, status="todo", priority="high")
                            task_queue.put({"id": str(uuid.uuid4()), "content": r_task, "agent_id": r_agent, "kanban_task_id": kanban_entry["id"]})
                except Exception as e:
                    log(f"⚠️ Watcher 例行任務讀取失敗: {e}")

        time.sleep(30)
