# -*- coding: utf-8 -*-
"""
ariel_bridge.py — ArielOS 中央橋接器 (模組化重構版)

架構說明：
  modules/config.py        → 常數、路徑、模型名稱
  modules/cerebellum.py    → 小腦邏輯 (call, cache, search, skill, distill)
  modules/personality.py   → PersonalityEngine, AgentDispatcher, spinal_chord_reflex
  modules/harness.py       → Shield, Harness, AuditLogger
  modules/evolution.py     → 夜間蒸餾, 好奇心排程, 進化守則
"""

# ── 標準庫 ────────────────────────────────────────────────────────────────────
import json, datetime, shutil, subprocess, queue, threading, uuid, re, time, logging
from pathlib import Path

# ── Flask ─────────────────────────────────────────────────────────────────────
from flask import Flask, request, jsonify, Response

# ── ArielOS 模組 ──────────────────────────────────────────────────────────────
from modules.config import (
    BASE_DIR, CACHE_PATH, KANBAN_DB_PATH,
    OLLAMA_API, CEREBELLUM_MODEL, INTENT_MODEL, CEREBELLUM_FALLBACK_MODEL, DISPATCHER_MODEL,
    log, ollama_post, IDLE_THRESHOLD, ROUTINES_PATH
)
from modules.harness import Shield, Harness, AuditLogger
from modules.personality import (
    AGENT_REGISTRY, PersonalityEngine, AgentDispatcher,
    load_agent_registry, spinal_chord_reflex, _sanitize_persona, _get_time_context
)
from modules.cerebellum import (
    cerebellum_call, _cached_cerebellum_simple, _set_cerebellum_simple_cache,
    cerebellum_semantic_check, cerebellum_style_transfer, cerebellum_skill_handler,
    cerebellum_fast_track_check, cerebellum_distill_context,
    analyze_task_intent, update_cache, search_web_worker
)
from modules.evolution import (
    generate_evolution_directive, get_evolution_context,
    perform_night_distillation, trigger_curiosity_idea, scheduler_worker
)
from modules.vector_memory import VM  # 向量記憶層 (ChromaDB + sentence-transformers)
from skill_manager import SkillManager
from memory_manager import MemoryManager

# ── 抑制警告 ──────────────────────────────────────────────────────────────────
logging.getLogger("primp").setLevel(logging.ERROR)

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
task_queue: queue.Queue = queue.Queue()
task_results: dict = {}

# ── 初始化全域實例 ────────────────────────────────────────────────────────────
load_agent_registry()
PE = PersonalityEngine(BASE_DIR)
SM = SkillManager(BASE_DIR)
MM = MemoryManager(BASE_DIR)
Dispatcher = AgentDispatcher(BASE_DIR)
KM_PATH = KANBAN_DB_PATH

# ── 看板管理器 (Inline, 依賴 KM_PATH) ────────────────────────────────────────
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
        except:
            return {"tasks": []}

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

# ── 閒置時間追蹤 ──────────────────────────────────────────────────────────────
last_activity_time_ref = [time.time()]  # 使用 list 以便跨函式修改

# ── 包裝函式：注入全域實例 ───────────────────────────────────────────────────

def _spinal_chord_reflex(query: str, agent_id: str):
    return spinal_chord_reflex(query, agent_id, AGENT_REGISTRY, PE, SM)

def _cerebellum_style_transfer(raw_answer: str, agent_id: str):
    return cerebellum_style_transfer(raw_answer, agent_id, AGENT_REGISTRY, PE)

def _cerebellum_fast_track_check(query: str, agent_id: str = None, **kwargs):
    return cerebellum_fast_track_check(query, agent_id or "unknown", AGENT_REGISTRY, PE, SM, **kwargs)

def _cerebellum_skill_handler(query: str, skill_desc: str, agent_id: str):
    return cerebellum_skill_handler(query, skill_desc, agent_id, SM, AGENT_REGISTRY, PE)

def _perform_night_distillation():
    return perform_night_distillation(AGENT_REGISTRY, MM, PE)

def _trigger_curiosity_idea():
    return trigger_curiosity_idea(AGENT_REGISTRY, task_queue, last_activity_time_ref)

def _scheduler_worker():
    return scheduler_worker(_perform_night_distillation, _trigger_curiosity_idea, KM, task_queue, last_activity_time_ref)

# ── 大腦執行員 ────────────────────────────────────────────────────────────────

def brain_worker():
    """🧠 大腦執行員：Phase 3 人格邏輯分離架構"""
    harness = Harness(BASE_DIR)
    audit = AuditLogger(BASE_DIR / "Shared_Vault" / "audit_log.jsonl")

    while True:
        task = task_queue.get()
        task_id, content = task['id'], task['content']
        agent_id = task.get('agent_id', 'unknown')
        agent_name = AGENT_REGISTRY.get(agent_id, {}).get('name', '未知代理')
        kanban_task_id = task.get('kanban_task_id')

        is_write_task = harness.needs_checkpoint(content)
        mode_label = "寫入模式 🛡️" if is_write_task else "唯讀模式 ⚡"
        log(f"🧠 [{agent_name}] {mode_label} | {content[:20]}...")

        try:
            shield = Shield(BASE_DIR)
            safe, reason = shield.scan(content)
            if not safe:
                task_results[task_id] = f"🛡️ [Shield Defense] {reason}"
                task_queue.task_done()
                continue

            if is_write_task:
                harness.create_checkpoint(task_id)

            memory_ctx = MM.build_memory_context(agent_id, content)
            # 📡 語意增強：從 ChromaDB 語意查詢補足關鍵字撈取不到的記憶
            if VM.is_ready:
                semantic_hits = VM.query_semantic(agent_id, content, top_k=3)
                if semantic_hits:
                    semantic_lines = "\n".join(
                        [f"- [{h['metadata'].get('type','?')}] {h['text']} (相似度:{h['score']})"
                         for h in semantic_hits]
                    )
                    semantic_block = f"[語意記憶]\n{semantic_lines}\n"
                    memory_ctx = (memory_ctx + "\n" + semantic_block) if memory_ctx else semantic_block
            if memory_ctx:
                log(f"🧠 LTM 記憶注入 (關鍵字+語意): {memory_ctx[:60]}...")

            session_context = MM.get_conversation_context(agent_id, max_history=10)
            evo_context = get_evolution_context(agent_id)

            # 🧪 上下文蒸餾
            if session_context and len(session_context) > 200:
                session_context = cerebellum_distill_context(session_context, content)

            prefix = ""
            if evo_context: prefix += evo_context + "\n"
            if memory_ctx: prefix += memory_ctx + "\n"
            if session_context: prefix += session_context + "\n"

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

            oc_path = shutil.which("openclaw")
            if not oc_path:
                task_results[task_id] = "🚨 Error: OpenClaw executable not found in PATH."
                task_queue.task_done()
                continue

            MAX_RETRIES = 3
            final_raw_answer = ""
            success = True

            for attempt in range(MAX_RETRIES):
                cmd_args = [oc_path, "agent", "--agent", "main", "--no-color", "--message", full_content]
                if attempt > 0:
                    log(f"🧠 [OpenClaw] Self-Correction Round {attempt+1}/{MAX_RETRIES}...")
                else:
                    log(f"🛠️ [OpenClaw Debug] Running: {oc_path} agent --agent main --no-color --message <content_len={len(full_content)}>")

                process = subprocess.run(cmd_args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=280)
                raw_answer = (process.stdout or "").strip()
                if not raw_answer:
                    raw_answer = (process.stderr or "").strip()
                final_raw_answer = raw_answer

                if not is_write_task:
                    break

                success, error_msg = harness.validate()
                if success:
                    break

                log(f"⚠️ 第 {attempt + 1} 次驗證失敗。錯誤:\n{error_msg}")

                # Cerebellum Hotfix Branch
                hotfix_success = False
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
                                f"系統拋出的錯誤訊息：\n{error_msg}\n"
                                f"請根據錯誤訊息修復這個 Bug。若缺少 import 請補上。\n"
                                f"「只」回傳修復後的完整 Python 程式碼，絕對不要包含任何 Markdown 標籤。"
                            )
                            fixed_code = cerebellum_call(prompt=hotfix_prompt, temperature=0.1, timeout=180, num_ctx=2048, num_predict=512)
                            fixed_code = re.sub(r"^```\w*\n?|\n?```$", "", fixed_code).strip()
                            if fixed_code:
                                with open(target_file, "w", encoding="utf-8") as f:
                                    f.write(fixed_code)
                                h_success, h_error_msg = harness.validate()
                                if h_success:
                                    log(f"✅ 小腦 Hotfix 成功！免除大腦重構 ({error_type})。")
                                    success = True
                                    hotfix_success = True
                                    final_raw_answer += f"\n\n[系統附註: 過程中有 {error_type}，已由小腦自動追蹤並完成修復: {error_file}]"
                                else:
                                    log("❌ 小腦 Hotfix 依然失敗，交回大腦處理。")
                        except Exception as e:
                            log(f"⚠️ 小腦 Hotfix 異常: {e}")

                if hotfix_success:
                    break

                harness.rollback(task_id)
                log("⚠️ 啟動 Brain Replan (大腦重新規劃)...")
                threading.Thread(target=generate_evolution_directive, args=(agent_id, content, error_msg, MM)).start()

                full_content = (
                    f"你上一次的實作失敗了。系統 Linter/編譯器 回報了以下錯誤：\n"
                    f"```\n{error_msg}\n```\n"
                    f"請仔細分析這個錯誤，確保語意與縮排正確，並嘗試使用不同的方法修正它。\n\n"
                    f"【原始任務】\n{content}"
                )

            raw_answer = final_raw_answer

            # Explicit Handoff Detection
            if "HANDOFF_TO_HUMAN:" in raw_answer:
                handoff_msg = raw_answer.split("HANDOFF_TO_HUMAN:")[1].strip()
                log(f"⏸️ [Handoff] Agent 觸發人機交接: {handoff_msg[:50]}")
                if kanban_task_id:
                    KM.update_task(kanban_task_id, {
                        "status": "waiting_for_user",
                        "logs": f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⏸️ 任務暫停等待指示\n原因: {handoff_msg}"
                    })
                final_answer = _cerebellum_style_transfer(
                    f"[Agent 需要您的協助]\n老闆，我在執行這個任務時遇到了顧慮，想先跟您確認：\n{handoff_msg}",
                    agent_id
                )
                task_results[task_id] = final_answer
                task_queue.task_done()
                continue

            if is_write_task and not success:
                raw_answer = f"⚠️ [經過 {MAX_RETRIES} 次驗證皆失敗] 已自動回滾狀態。最後一次錯誤：\n{error_msg}\n\n{raw_answer}"

            # 🎭 多代理博弈：Reviewer 審查循環（僅 high-priority 任務）
            task_priority = task.get('priority', 'medium')
            if task_priority == 'high' and raw_answer and success:
                log("🎭 [Reviewer] 高優先任務觸發審查循環...")
                reviewer_soul_path = BASE_DIR / "Shared_Vault" / "roles" / "reviewer.soul.md"
                reviewer_soul = reviewer_soul_path.read_text(encoding="utf-8") if reviewer_soul_path.exists() else ""
                review_prompt = (
                    f"{reviewer_soul}\n\n"
                    f"針對以下 Worker 的產出進行審查。\n"
                    f"【任務請求】\n{content[:500]}\n\n"
                    f"【Worker 的產出】\n{raw_answer[:2000]}\n\n"
                    f"請依照你的輸出格式回傳審查結果。"
                )
                try:
                    review_result = cerebellum_call(
                        prompt=review_prompt, temperature=0.1, timeout=120,
                        num_ctx=4096, num_predict=400
                    )
                    log(f"🎭 [Reviewer] 審查: {review_result[:80]}...")

                    if "[VERDICT]: REJECT" in review_result:
                        log("🚨 [Reviewer] REJECT，觸發 Self-Correction...")
                        correction_prompt = (
                            f"你之前的產出被 Reviewer 拒絕了。\n"
                            f"審查意見：\n{review_result}\n\n"
                            f"請修正所有問題，重新輸出完整結果。原始任務：{content[:300]}"
                        )
                        corrected = cerebellum_call(
                            prompt=correction_prompt, temperature=0.1, timeout=120,
                            num_ctx=4096, num_predict=800
                        )
                        if corrected:
                            raw_answer = corrected
                            log("✅ [Reviewer] Self-Correction 完成，更新產出。")
                            if kanban_task_id:
                                KM.update_task(kanban_task_id, {
                                    "logs": f"[Reviewer REJECT+修正] {review_result[:200]}"
                                })
                    else:
                        log("✅ [Reviewer] PASS，審查通過。")
                except Exception as e:
                    log(f"⚠️ [Reviewer] 審查回路異常: {e}")

            final_answer = _cerebellum_style_transfer(raw_answer, agent_id)
            audit.append(task_id, content, final_answer, success, agent_id=agent_id)

            if kanban_task_id:
                log_snippet = final_answer[:300] + "..." if len(final_answer) > 300 else final_answer
                KM.update_task(kanban_task_id, {
                    "status": "done",
                    "logs": f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ 執行完成\n{log_snippet}"
                })
                log(f"🗂️ Kanban 已更新: {kanban_task_id[:8]}... → done")
                notify_kanban_clients()

            MM.append_chat(agent_id, "user", content)
            MM.append_chat(agent_id, "assistant", final_answer)
            threading.Thread(target=MM._compress_old_chats, args=(agent_id,)).start()
            threading.Thread(target=update_cache, args=(content, final_answer)).start()
            task_results[task_id] = final_answer

        except Exception as e:
            err_msg = f"🚨 大腦異常: {str(e)}"
            if kanban_task_id:
                KM.update_task(kanban_task_id, {
                    "status": "done",
                    "logs": f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ❌ 執行失敗\n{err_msg}"
                })
            task_results[task_id] = err_msg

        task_queue.task_done()


threading.Thread(target=brain_worker, daemon=True).start()

# ── Kanban SSE ────────────────────────────────────────────────────────────────

kanban_clients = []

def notify_kanban_clients():
    dead_clients = []
    for q in kanban_clients:
        try: q.put_nowait({"type": "update", "data": KM.get_all()})
        except queue.Full: dead_clients.append(q)
    for q in dead_clients:
        kanban_clients.remove(q)

# ── Flask API Routes ──────────────────────────────────────────────────────────

@app.route('/v1/harness/night-mode', methods=['POST'])
def trigger_night_mode():
    result = _perform_night_distillation()
    return jsonify({"status": "success", "message": result})

@app.route('/v1/harness/snapshot', methods=['POST'])
def trigger_snapshot():
    try:
        import tarfile
        from datetime import datetime
        backups_dir = BASE_DIR / "backups"
        backups_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_path = backups_dir / f"snapshot_{ts}.tar.gz"
        
        excludes = {"Shared_Vault/Memory", "Shared_Vault/chroma_db", "backups", "__pycache__", ".git", ".env"}
        def _exclude(tarinfo):
            for exc in excludes:
                if exc in tarinfo.name.replace("\\", "/"):
                    return None
            return tarinfo
            
        with tarfile.open(snap_path, "w:gz") as tar:
            tar.add(BASE_DIR, arcname="ArielOS", filter=_exclude)
            
        return jsonify({"status": "success", "message": f"快照建立成功: {snap_path.name}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/v1/harness/reload-agents', methods=['POST'])
def reload_agents():
    load_agent_registry()
    PE.invalidate()
    return jsonify({"status": "success", "message": f"Agents reloaded. Total: {len(AGENT_REGISTRY)}", "agents": list(AGENT_REGISTRY.keys())})

@app.route('/v1/team/dispatch', methods=['POST'])
def api_dispatch_task():
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
    if task_id in task_results:
        return jsonify({"status": "completed", "result": task_results.pop(task_id)})
    return jsonify({"status": "processing"})

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    global last_activity_time_ref
    try:
        last_activity_time_ref[0] = time.time()
        data = request.json
        user_input = data['messages'][-1]['content']
        agent_id = data.get('agent_id', 'unknown')
        origin = data.get('origin', '')
        gas_url = data.get('gas_url') or ''
        agent_name = AGENT_REGISTRY.get(agent_id, {}).get('name', '未知')
        log(f"📨 收到來自 [{agent_name}] 的請求{' (看板執行器)' if origin == 'kanban_poller' else ''}")

        if user_input.startswith("dispatch:"):
            try:
                _, role, payload = user_input.split(":", 2)
                task_id = f"task_{int(time.time())}"
                result = Dispatcher.dispatch(task_id, role.strip(), payload.strip())
                return jsonify({"choices": [{"message": {"content": f"👮 [Dispatcher Result]\n{result}"}}]})
            except ValueError:
                return jsonify({"choices": [{"message": {"content": "❌ 格式錯誤。請使用: dispatch:role:instruction"}}]})

        cached = cerebellum_semantic_check(user_input)
        if cached and cached != "OLLAMA_BUSY":
            return jsonify({"choices": [{"message": {"content": f"[Ariel 智慧快取]\n{cached}"}}]})

        ollama_busy = (cached == "OLLAMA_BUSY")
        if ollama_busy:
            log("⚡ Ollama 忙碌，跳過 FastTrack 直接入列大腦")

        reflex_ans = _spinal_chord_reflex(user_input, agent_id)
        if reflex_ans:
            log(f"⚡ 脊髓反射命中: {reflex_ans}")
            return jsonify({"choices": [{"message": {"content": reflex_ans}}]})

        intent_type, fast_ans = (None, None)
        if not ollama_busy:
            intent_type, fast_ans = _cerebellum_fast_track_check(user_input, agent_id, gas_url=gas_url)

        if intent_type == "SIMPLE":
            log(f"⚡ Fast Track [SIMPLE]: {fast_ans[:20]}...")
            MM.append_chat(agent_id, "user", user_input)
            MM.append_chat(agent_id, "assistant", fast_ans)
            threading.Thread(target=MM._compress_old_chats, args=(agent_id,)).start()
            return jsonify({"choices": [{"message": {"content": fast_ans}}]})

        if intent_type in ("SEARCH", "SKILL"):
            kanban_entry = KM.add_task(
                title=user_input[:80] + ('...' if len(user_input) > 80 else ''),
                agent_id=agent_id, status="doing", priority="low"
            )
            result_snippet = fast_ans[:300] + '...' if len(fast_ans) > 300 else fast_ans
            KM.update_task(kanban_entry['id'], {"status": "done", "logs": f"[小腦 {intent_type}] {result_snippet}"})
            log(f"⚡ Fast Track [{intent_type}] 完成: {fast_ans[:20]}...")
            notify_kanban_clients()
            MM.append_chat(agent_id, "user", user_input)
            MM.append_chat(agent_id, "assistant", fast_ans)
            threading.Thread(target=MM._compress_old_chats, args=(agent_id,)).start()
            return jsonify({"choices": [{"message": {"content": fast_ans}}]})

        if intent_type is not None:
            return jsonify({"choices": [{"message": {"content": fast_ans}}]})

        kanban_task_id = None
        if origin != 'kanban_poller':
            kanban_entry = KM.add_task(
                title=user_input[:80] + ('...' if len(user_input) > 80 else ''),
                agent_id=agent_id, status="doing", priority="medium"
            )
            kanban_task_id = kanban_entry['id']
            log(f"🗂️ Kanban Job 建立: [{agent_name}] {user_input[:30]}...")
            notify_kanban_clients()

        tid = str(uuid.uuid4())
        task_queue.put({'id': tid, 'content': user_input, 'agent_id': agent_id, 'kanban_task_id': kanban_task_id})
        log(f"✅ 任務 {tid} 已入列 (腦部處理中)")
        return jsonify({"task_id": tid, "status": "queued"}), 202

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/v1/kanban/stream')
def kanban_stream():
    def event_stream():
        q = queue.Queue(maxsize=10)
        kanban_clients.append(q)
        try:
            yield f"data: {json.dumps(KM.get_all())}\n\n"
            while True:
                message = q.get(timeout=30)
                yield f"data: {json.dumps(message['data'])}\n\n"
        except queue.Empty:
            yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            if q in kanban_clients:
                kanban_clients.remove(q)
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/kanban')
def kanban_ui():
    return app.send_static_file('kanban.html')

@app.route('/v1/kanban/tasks', methods=['GET'])
def get_kanban_tasks():
    return jsonify(KM.get_all())

@app.route('/v1/kanban/tasks', methods=['POST'])
def add_kanban_task():
    try:
        data = request.json
        title = data.get('title', 'Unknown Task')
        analysis = analyze_task_intent(title)
        task = KM.add_task(title=title, agent_id=data.get('agent_id', 'agent1'), status=data.get('status', 'todo'), priority=analysis.get('priority', 'medium'))
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

@app.route('/v1/skills', methods=['GET'])
def list_skills():
    return jsonify({"installed": SM.list_installed(), "catalog": SM.list_catalog()})

@app.route('/v1/skills/search', methods=['POST'])
def search_skills():
    query = request.json.get('query', '')
    return jsonify(SM.search_skill_online(query))

@app.route('/v1/skills/install', methods=['POST'])
def install_skill_api():
    skill_info = request.json
    success = SM.install_skill(skill_info)
    return jsonify({"status": "installed" if success else "failed"})

@app.route('/v1/skills/<name>', methods=['DELETE'])
def remove_skill(name):
    success = SM.remove_skill(name)
    return jsonify({"status": "removed" if success else "not_found"})

# ── 啟動 ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    log(f"ArielOS 智慧總部 v2.0 (模組化版) 啟動成功 | 路徑鎖定: {BASE_DIR}")
    log(f"🧠 小腦模型配置 | 主要: {CEREBELLUM_MODEL} | 快取分類: {INTENT_MODEL} | 備用: {CEREBELLUM_FALLBACK_MODEL}")
    log(f"🤖 Dispatcher 模型: {DISPATCHER_MODEL}")
    log(f"📦 已載入模組: config, harness, personality, cerebellum, evolution")
    threading.Thread(target=_scheduler_worker, daemon=True).start()
    from waitress import serve
    log("🚀 啟動 Waitress 生產級伺服器 (Port 28888)...")
    serve(app, host='0.0.0.0', port=28888, threads=16)
