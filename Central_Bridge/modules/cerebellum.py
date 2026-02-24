# -*- coding: utf-8 -*-
"""
modules/cerebellum.py — ArielOS 小腦核心模組

包含：cerebellum_call, cache, semantic_check, fast_track, style_transfer,
      skill_handler, web_search, distill_context, analyze_task_intent, update_cache
"""

import re
import json
import time
import datetime
import threading as _threading
import subprocess
import uuid
import sys
from pathlib import Path
from ddgs import DDGS

from .config import (
    OLLAMA_API, CEREBELLUM_MODEL, CEREBELLUM_FALLBACK_MODEL, INTENT_MODEL,
    CACHE_PATH, DATA_SANDBOX_PATH, log, ollama_post
)

# ── 並發保護 ──────────────────────────────────────────────────────────────────
_CEREBELLUM_SEMAPHORE = _threading.Semaphore(2)

# ── SIMPLE 問題快取 ───────────────────────────────────────────────────────────
_SIMPLE_CACHE: dict = {}
_SIMPLE_CACHE_TTL = 300  # 5 分鐘


def _cached_cerebellum_simple(cache_key: str):
    entry = _SIMPLE_CACHE.get(cache_key)
    if entry and time.time() < entry[1]:
        log(f"⚡ [SimpleCache] 命中快取: {cache_key[:30]}")
        return entry[0]
    return None


def _set_cerebellum_simple_cache(cache_key: str, answer: str):
    _SIMPLE_CACHE[cache_key] = (answer, time.time() + _SIMPLE_CACHE_TTL)
    expired = [k for k, (_, ts) in _SIMPLE_CACHE.items() if time.time() >= ts]
    for k in expired:
        _SIMPLE_CACHE.pop(k, None)


# ── 統一呼叫介面 ──────────────────────────────────────────────────────────────

def cerebellum_call(prompt: str, temperature: float = 0.3, timeout: int = 180,
                    num_ctx: int = 2048, num_predict: int = 256, model: str = None) -> str:
    """🧠 小腦統一呼叫介面（含 Semaphore 保護、精簡 Context 設定、自動模型降級）

    各場景建議設定：
    - 意圖分類:   num_ctx=2048, num_predict=80
    - 關鍵字萃取: num_ctx=1024, num_predict=30
    - 快取比對:   num_ctx=2048, num_predict=10
    - 風格轉移:   num_ctx=4096, num_predict=600

    自動降級：若指定 model (或 CEREBELLUM_MODEL) 超時或不存在，自動改用 CEREBELLUM_FALLBACK_MODEL。
    """
    target_model = model if model else CEREBELLUM_MODEL
    payload = {
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict}
    }
    with _CEREBELLUM_SEMAPHORE:
        try:
            resp = ollama_post(OLLAMA_API, json={**payload, "model": target_model}, timeout=timeout)
            return resp.json().get('response', '').strip()
        except Exception as e:
            log(f"⚠️ [{target_model}] 失敗，降級至 {CEREBELLUM_FALLBACK_MODEL}: {e}")
        resp = ollama_post(OLLAMA_API, json={**payload, "model": CEREBELLUM_FALLBACK_MODEL}, timeout=timeout)
        return resp.json().get('response', '').strip()


# ── 搜尋 ──────────────────────────────────────────────────────────────────────

def extract_search_keywords(query: str) -> str:
    """萃取搜尋關鍵字 (含 CPU 備位方案)"""
    try:
        # ⚡ CPU Pre-filter: 極簡問題直接去頭去尾 (不啟動 GPU)
        q_clean = query.strip().strip('?？').lower()
        if len(q_clean) < 10:
            return q_clean
            
        keywords = cerebellum_call(
            prompt=(
                f"將以下自然語言問句轉換成精確的搜尋引擎關鍵字（2~5個詞），只輸出關鍵字，用空格分隔，不要解釋。\n"
                f"問句：『{query}』\n關鍵字："
            ),
            temperature=0, timeout=12, num_ctx=1024, num_predict=30
        )
        keywords = keywords.split('\n')[0].strip().strip('"').strip("'").strip('`')
        if keywords and len(keywords) > 1:
            log(f"🔑 關鍵字萃取: '{query}' → '{keywords}'")
            return keywords
    except Exception as e:
        log(f"⚠️ 關鍵字萃取失敗 (GPU Timeout/Error): {e}")
        
    # 🧪 CPU Fallback: 簡單的分詞與贅字移除 (非常粗糙但比掛掉好)
    stop_words = ["幫我", "查詢", "搜尋", "一下", "在哪", "是什麼", "如何", "多少", "的", "個"]
    k_list = [w for w in query.replace("?", "").replace(" ", "") if w not in stop_words]
    fallback_k = "".join(k_list[:10])
    log(f"🔑 關鍵字萃取 (CPU Fallback): {fallback_k}")
    return fallback_k


def google_ai_search_worker(query: str) -> str | None:
    """🌐 使用 Playwright 抓取 Google AI 摘要 (SGE)"""
    from playwright.sync_api import sync_playwright
    log(f"🌐 [Google AI Search] 啟動抓取: {query[:50]}...")
    
    try:
        from playwright_stealth import Stealth
    except ImportError as e:
        import sys
        Stealth = None
        log(f"⚠️ 未安裝 playwright-stealth (或路徑問題: {e})")
        log(f"🧠 目前執行環境 Python: {sys.executable}")
        log(f"🧠 環境路徑 (sys.path): {sys.path[:3]}...") # 只列出前幾個路徑避免過長
        log("👉 建議針對此路徑執行: python -m pip install playwright-stealth")
    
    try:
        if Stealth:
            playwright_cm = Stealth().use_sync(sync_playwright())
        else:
            playwright_cm = sync_playwright()
            
        with playwright_cm as p:
            # 使用本機真實 Chrome 與持久化使用者設定檔 (累積 Cookie 信任度)
            user_data_dir = str(DATA_SANDBOX_PATH / "ariel_chrome_profile_google")

            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="chrome", # 強制使用本機的 Google Chrome
                headless=False, # 😈 啟動實體視窗 (避免被標記為 Headless 機器人)
                args=['--disable-blink-features=AutomationControlled'],
                viewport={'width': 1280, 'height': 800}
            )
            page = context.pages[0] if context.pages else context.new_page()
            
            # 導向 Google 搜尋
            search_url = f"https://www.google.com/search?q={query}"
            page.goto(search_url, timeout=30000)
            
            # 🛡️ 檢查是否遭到 Google CAPTCHA 阻擋
            if page.locator('form[action="/sorry/index"]').count() > 0 or "sorry/index" in page.url:
                log("⚠️ [Google AI] 遭到 Google CAPTCHA (機器人驗證) 阻擋，強制觸發回退機制。")
                context.close()
                return None
                
            # 確保主要搜尋結果區塊已載入
            try:
                page.wait_for_selector('#search', timeout=10000)
            except Exception:
                log("⚠️ [Google AI] 搜尋主區塊超時未載入，可能遭到阻擋。")
            
            # 等待 AI 摘要出現 (嘗試不同選擇器)
            try:
                # 1. 嘗試等待 aria-label (設定合理的 15 秒，避免卡死)
                page.wait_for_selector('[aria-label*="AI 摘要"]', timeout=15000)
                
                # 找到容器
                container = page.locator('[aria-label*="AI 摘要"]').locator('..')
                
                # 抓取主要文字內容 (通常在 MUF9yc 或類似標籤中)
                # 這裡使用更通用的方式：抓取區塊內的段落
                paragraphs = container.locator('div[data-content-type="1"], span').all_text_contents()
                summary = "\n".join([p.strip() for p in paragraphs if len(p.strip()) > 10])
                
                if not summary:
                    # 備位方案：抓取標題下方的第一個大文字塊
                    try:
                        summary = page.locator('div.MUF9yc').first.inner_text(timeout=2000)
                    except Exception:
                        pass

                if summary:
                    log(f"✅ [Google AI] 成功獲取摘要 ({len(summary)} 字元)")
                    return f"[Google AI 搜尋結果]\n{summary.strip()}"
                
            except Exception as e:
                log(f"⚠️ [Google AI] 未發現 AI 摘要區塊或超時: {str(e)[:50]}")
            
            context.close()
    except Exception as e:
        log(f"🚨 [Google AI] 瀏覽器實例啟動失敗: {e}")
    return None


def perplexity_search_worker(query: str) -> str | None:
    """🌐 使用 Playwright 抓取 Perplexity AI 摘要"""
    from playwright.sync_api import sync_playwright
    log(f"🌐 [Perplexity AI] 啟動抓取: {query[:50]}...")
    
    try:
        from playwright_stealth import Stealth
    except ImportError as e:
        Stealth = None
        log(f"⚠️ [Perplexity] 模組載入失敗: {e}")
    
    try:
        if Stealth:
            playwright_cm = Stealth().use_sync(sync_playwright())
        else:
            playwright_cm = sync_playwright()
            
        with playwright_cm as p:
            user_data_dir = str(DATA_SANDBOX_PATH / "ariel_chrome_profile_perplexity")

            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="chrome", # 強制使用本機的 Google Chrome
                headless=False, # 😈 啟動實體視窗，完全抹除 Headless 特徵
                args=['--disable-blink-features=AutomationControlled'],
                viewport={'width': 1280, 'height': 800}
            )
            page = context.pages[0] if context.pages else context.new_page()
            
            # Perplexity URL 格式
            search_url = f"https://www.perplexity.ai/search?q={query}"
            page.goto(search_url, timeout=40000)
            
            # 🛡️ 檢查是否遭到 Cloudflare 阻擋
            if "Just a moment" in page.title() or "challenge" in page.url:
                log("⚠️ [Perplexity AI] 遭到 Cloudflare 機器人驗證阻擋，觸發回退機制。")
                context.close()
                return None

            try:
                # 等待回答開始生成 (通常是有一個特定的類名或文字)
                # Perplexity 的結構較深，我們抓取 Proxima 或類似容器的文字
                page.wait_for_selector('.prose', timeout=20000)
                
                # 抓取回答內容
                answer_elements = page.locator('.prose').all_text_contents()
                summary = "\n".join([a.strip() for a in answer_elements if len(a.strip()) > 20])
                
                if summary:
                    log(f"✅ [Perplexity AI] 成功獲取摘要 ({len(summary)} 字元)")
                    return f"[Perplexity AI 搜尋結果]\n{summary.strip()}"
            except Exception as e:
                log(f"⚠️ [Perplexity AI] 抓取超時或未發現回答: {str(e)[:50]}")
            
            context.close()
    except Exception as e:
        log(f"🚨 [Perplexity AI] 異常: {e}")
    return None


def search_web_worker(query: str) -> str:
    """🚀 Phase 8: 混合式共識搜尋 (Google AI + Perplexity AI + DDGS)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    log(f"🔍 [Search Worker] 啟動共識搜尋: {query[:50]}...")
    
    ai_results = []
    # 🏃 啟動並發抓取：小腦同時派出多個探針
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(google_ai_search_worker, query): "Google AI",
            executor.submit(perplexity_search_worker, query): "Perplexity AI"
        }
        
        for future in as_completed(futures):
            engine_name = futures[future]
            try:
                res = future.result()
                if res:
                    ai_results.append(res)
                    # 💡 如果已經拿到一個高品質結果，可以考慮提早回傳 (Race Mode)
                    # 但為了共識，我們這裡等全部跑完或第一個成功即回傳
                    log(f"🎯 [Search Worker] {engine_name} 搶先擊中！")
                    return res
            except Exception as e:
                log(f"⚠️ [Search Worker] {engine_name} 支線故障: {e}")

    # 3. 備位方案: DDGS + CPU 程式化過濾 (所有 AI 都失敗時)
    log("🔍 [Search Worker] 所有 AI 搜尋均失效，執行 DDGS + CPU 程式化過濾...")
    try:
        search_keywords = extract_search_keywords(query)
        results = DDGS().text(search_keywords, max_results=10)
        if not results:
            return "Unable to find relevant information from the web."
            
        raw_data_path = DATA_SANDBOX_PATH / f"search_raw_{uuid.uuid4().hex[:8]}.json"
        with open(raw_data_path, "w", encoding="utf-8") as f:
            json.dump(list(results), f, ensure_ascii=False)
            
        prompt = (
            f"你現在是能直接寫程式過濾資料的搜尋代理人。使用者詢問：『{query}』\n"
            f"我已將 10 筆搜尋結果存入 JSON 檔案：{raw_data_path}\n"
            "格式為 [{{'title': '...', 'body': '...', 'href': '...'}}...]\n"
            "請撰寫一段 Python 程式碼，讀取該檔案，分析 body 欄位找出問題的答案，並使用 print() 輸出『簡潔且精確的結論』。\n"
            "規則：\n"
            "1. 僅輸出 Python 程式碼，不加 ```python 標籤。\n"
            "2. **讀取 JSON 或任何檔案時，務必使用 `open(..., encoding='utf-8')` 解碼。**\n"
            "3. 只 print 最精華的繁體中文結果，不要 print 原始陣列。"
        )
        script_code = cerebellum_call(prompt=prompt, temperature=0.1, timeout=180, num_ctx=2048, num_predict=1024)
        # 🛡️ 嘗試精準提取 markdown 內的程式碼，避免 LLM 的開場白導致執行失敗
        code_match = re.search(r"```(?:python)?\n(.*?)\n```", script_code, re.DOTALL | re.IGNORECASE)
        if code_match:
            script_code = code_match.group(1).strip()
        else:
            script_code = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", script_code.strip(), flags=re.MULTILINE)
            if "import" in script_code:
                script_code = script_code[script_code.find("import"):]
        
        script_path = DATA_SANDBOX_PATH / f"search_prog_{uuid.uuid4().hex[:8]}.py"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_code)
            
        log(f"💻 [Sandbox] 執行搜尋過濾腳本: {script_path.name}")
        res = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=15, cwd=str(DATA_SANDBOX_PATH)
        )
        
        try:
            script_path.unlink()
            raw_data_path.unlink()
        except: pass

        if res.returncode == 0:
            output = res.stdout.strip()
            if not output:
                output = "程式碼執行完畢，但未印出任何結論。"
            return f"[網路搜尋結果]\n{output}"
        else:
            log(f"⚠️ 搜尋過濾腳本失敗: {res.stderr}")
            return f"Error filtering search results: {res.stderr.strip()}"
            
    except Exception as e:
        log(f"⚠️ 搜尋失敗: {e}")
        return f"Error performing search: {e}"


def programmatic_data_worker(query: str) -> str:
    """🚀 Phase 8: CPU-Driven Programmatic Tool Calling (Sandbox Filtering)"""
    log(f"💻 [Programmatic Worker] 啟動程式化沙盒處理: {query[:50]}...")
    try:
        instruction = (
            f"你現在是一名資深資料工程師。使用者的需求是：『{query}』\n"
            "請直接撰寫一段 Python 程式碼，在本地執行此資料過濾/排序/比對任務。\n"
            "規則：\n"
            "1. 僅輸出 Python 程式碼，不加 ```python 或任何額外說明。\n"
            "2. 使用 urllib 或 requests 撈取公開資料（如需上網），或使用 OS 模組讀寫必要的檔案。\n"
            "3. **讀取任何本地檔案時，務必在 open() 中加上 encoding='utf-8' 參數。**\n"
            "4. 在程式碼最後，使用 print() 輸出『最簡潔的精華結論』，這個 print 的結果將會直接交給使用者。\n"
            "5. 確保程式碼沒有無窮迴圈，並且能快速執行完畢。"
        )
        script_code = cerebellum_call(prompt=instruction, temperature=0.1, timeout=180, num_ctx=2048, num_predict=1024)
        
        # 🛡️ 嘗試精準提取 markdown 內的程式碼，避免 LLM 的開場白導致執行失敗
        code_match = re.search(r"```(?:python)?\n(.*?)\n```", script_code, re.DOTALL | re.IGNORECASE)
        if code_match:
            script_code = code_match.group(1).strip()
        else:
            script_code = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", script_code.strip(), flags=re.MULTILINE)
            if "import" in script_code:
                script_code = script_code[script_code.find("import"):]
        
        script_path = DATA_SANDBOX_PATH / f"prog_{uuid.uuid4().hex[:8]}.py"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_code)
            
        log(f"💻 [Sandbox] 執行腳本: {script_path.name}")
        res = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=15, cwd=str(DATA_SANDBOX_PATH)
        )
        
        # 清理沙盒
        try: script_path.unlink()
        except: pass

        if res.returncode == 0:
            output = res.stdout.strip()
            if len(output) > 2000:
                output = output[:2000] + "\\n...(截斷)"
            if not output:
                output = "程式碼執行完畢，但未產生任何輸出。"
            return f"[程式化分析結果]\\n{output}"
        else:
            log(f"⚠️ [Sandbox] 腳本執行失敗: {res.stderr}")
            return f"Error executing programmatic data analysis: {res.stderr.strip()}"
            
    except subprocess.TimeoutExpired:
        log("❌ [Sandbox] 腳本執行逾時(>15s)！")
        return "Timeout error: Programmatic script took too long to execute."
    except Exception as e:
        log(f"⚠️ 程式化處理失敗: {e}")
        return f"Error in programmatic worker: {e}"


# ── 快取語意檢查 ──────────────────────────────────────────────────────────────

def cerebellum_semantic_check(query: str):
    """🚀 小腦門衛：由 Ollama 判定語意意圖 (邏輯增強版)"""
    cached = _cached_cerebellum_simple(query)
    if cached:
        return cached

    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            records = data.get("records", [])
            if not records:
                return None
            now = datetime.datetime.now()
            valid_records = [r for r in records if now < datetime.datetime.fromisoformat(r['expires_at'])]
            target_pool = valid_records[-10:]
            if not target_pool:
                return None

            # 關鍵字重疊預篩選：只抓出有字元重疊的快取項目
            query_chars = set(query.replace(" ", ""))
            overlapping_records = []
            for i, r in enumerate(target_pool):
                r_chars = set(r['query'].replace(" ", ""))
                overlap_ratio = len(query_chars & r_chars) / max(len(query_chars | r_chars), 1)
                
                # ⚡ [CPU Ultra Hit] 相似度極高 (>85%)，直接命中，跳過 LLM 判定
                if overlap_ratio >= 0.85:
                    log(f"⚡ [CPU Ultra Hit] 相似度高達 {overlap_ratio:.2f}，直接命中 ID:{i}")
                    return r['summary']
                
                if overlap_ratio >= 0.35:
                    overlapping_records.append((i, r))

            if not overlapping_records:
                log("🛡️ [SemanticCache] 無足夠重疊，跳過 LLM 判定")
                return None

            cache_context = "\n".join([f"ID:{i} | 問題:{r['query']}" for i, r in overlapping_records])
            instruction = (
                f"你現在是 ArielOS 的超嚴格語意門衛。快取清單如下：\n{cache_context}\n\n"
                f"現在老闆問了：『{query}』\n"
                "【判斷標準 — 必須三項全部相同才可命中】\n"
                "  1. 主題/領域 完全相同（如：天氣 ≠ 法律，技能 ≠ 進度）\n"
                "  2. 地點/對象 完全相同\n"
                "  3. 行動/意圖 完全相同（如：學習技能 ≠ 查詢進度）\n\n"
                "【終極指令】\n"
                "絕對不允許任何解釋或廢話。\n"
                "如果上述清單中有完全吻合的項目，請你嚴格按照以下格式輸出：\n"
                "[MATCH_ID:數字]\n"
                "如果沒有任何一個項目符合，或是你不確定，請嚴格按照以下格式輸出：\n"
                "[NO]\n"
            )
            judgment = cerebellum_call(prompt=instruction, temperature=0, timeout=25, num_ctx=1024, num_predict=20)
            
            if "[NO]" in judgment.upper():
                return None
                
            match = re.search(r'\[MATCH_ID:(\d+)\]', judgment, re.IGNORECASE)
            if match:
                idx = int(match.group(1))
                if 0 <= idx < len(target_pool):
                    log(f"⚡ 小腦確認語意命中 ID:{idx}")
                    return target_pool[idx]['summary']
            
            log(f"⚠️ [SemanticCache] LLM 回傳格式錯誤或無命中: {judgment[:20]}")
            return None
    except Exception as e:
        log(f"⚠️ 小腦門衛異常: {e}")
        if "timed out" in str(e).lower() or "read timeout" in str(e).lower():
            return "OLLAMA_BUSY"
    return None


# ── 風格轉移 ──────────────────────────────────────────────────────────────────

def cerebellum_style_transfer(raw_answer: str, agent_id: str, agent_registry: dict, pe) -> str:
    """🚀 小腦風格轉移：將大腦的純邏輯答案轉化為代理人人格"""
    from .personality import _sanitize_persona
    soul = pe.load_soul(agent_id)
    agent_name = agent_registry.get(agent_id, {}).get("name", "Agent")
    if not soul:
        return _sanitize_persona(raw_answer, agent_name)

    # 🛡️ 如果是系統錯誤訊息或完全找不到資料，直接放行，避免 AI 套用語氣產生幻覺
    error_signatures = [
        "Error performing search:",
        "Error filtering search:",
        "Error executing programmatic data analysis:",
        "Error in programmatic worker:",
        "Timeout error:",
        "程式碼執行完畢，但未",
        "Unable to find relevant information",
        "Traceback ("
    ]
    if any(sig in raw_answer for sig in error_signatures):
        return f"[{agent_name} 系統回報]\n{raw_answer}"

    if len(raw_answer) > 3000:
        try:
            intro = cerebellum_call(
                prompt=(f"你是 {agent_name}。請用你獨特的說話風格，只寫一句話向老闆報告以下任務已完成。"
                        f"任務摘要（前200字）：{raw_answer[:200]}"),
                temperature=0.4, timeout=120, num_ctx=1024, num_predict=60
            )
            if intro:
                return f"{_sanitize_persona(intro, agent_name)}\n\n{_sanitize_persona(raw_answer, agent_name)}"
        except Exception as e:
            log(f"⚠️ 大輸出前言生成失敗: {e}")
        return _sanitize_persona(raw_answer, agent_name)

    # 避免複誦角色設定與幻覺
    instruction = (
        f"你現在扮演『{agent_name}』。你的個性如下：\n"
        f"【角色特質】\n{soul[:300]}\n\n"
        f"【任務：文字潤飾】\n"
        f"請使用你的口吻與第一人稱『我』，將下方【待潤飾的原文】重新改寫，讓它聽起來像是你說的話。\n"
        f"【強制規則】\n"
        f"1. 嚴禁在回答中提到「這是我的靈魂設定」、「我是XXX」等自我介紹的廢話。\n"
        f"2. 嚴禁加上「好的」、「以下是」等前言。\n"
        f"3. 嚴禁修改原文中的程式碼或關鍵數值資料。\n"
        f"4. 將原文的 'Ariel' 或 'ArielOS' 改為『{agent_name}』。\n"
        f"5. **必須使用繁體中文 (Traditional Chinese) 回答**，即便原文是簡體或英文也必須翻譯潤飾。\n"
        f"6. 直接輸出你改寫後的結果，絕對不要包含任何 Markdown 標記，也不要輸出 JSON。\n\n"
        f"【待潤飾的原文】\n{raw_answer}"
    )
    try:
        styled = cerebellum_call(prompt=instruction, temperature=0.7, timeout=120, num_ctx=4096, num_predict=600)
        if styled:
            # 清理 Gemma 可能會產生的 ``` 標記
            import re
            styled = re.sub(r"^```\w*\n?|\n?```$", "", styled.strip(), flags=re.MULTILINE)
            return _sanitize_persona(styled, agent_name)
    except Exception as e:
        log(f"⚠️ 風格轉移失敗: {e}")
    return _sanitize_persona(raw_answer, agent_name)


# ── 技能路由 ──────────────────────────────────────────────────────────────────

def cerebellum_skill_handler(query: str, skill_desc: str, agent_id: str, sm, agent_registry: dict, pe, **kwargs) -> str | None:
    """🔧 Phase 13: 小腦技能路由"""
    matched = sm.find_matching_skill(skill_desc)
    if matched:
        log(f"🔧 技能命中 (關鍵字): {matched['name']}")
        installed_names = [s['name'] for s in sm.list_installed()]
        if matched['name'] not in installed_names:
            sm.install_skill(matched)
        result = sm.execute_skill(matched, query, **kwargs)
        if result:
            return cerebellum_style_transfer(result, agent_id, agent_registry, pe)

    if not matched:
        matched = sm.find_skill_by_llm(skill_desc)
        if matched:
            log(f"🔧 技能命中 (LLM): {matched['name']}")
            installed_names = [s['name'] for s in sm.list_installed()]
            if matched['name'] not in installed_names:
                sm.install_skill(matched)
            result = sm.execute_skill(matched, query, **kwargs)
            if result:
                return cerebellum_style_transfer(result, agent_id, agent_registry, pe)

    log(f"🌐 線上搜尋技能: {skill_desc}")
    candidates = sm.search_skill_online(skill_desc)
    if candidates:
        best = candidates[0]
        log(f"📦 嘗試安裝線上技能: {best['name']}")
        if sm.install_skill(best):
            result = sm.execute_skill(best, query, **kwargs)
            if result:
                return cerebellum_style_transfer(result, agent_id, agent_registry, pe)

    log(f"⚠️ 技能路由完全失敗: {query[:40]}...")
    return f"報告老闆，我剛才試著運算或尋找此項技能，但遭遇了連線問題或是硬體核心超時。建議您稍後重試，或是確認本機的 MCP 環境是否正常。"


# ── Fast Track ────────────────────────────────────────────────────────────────

def cerebellum_fast_track_check(query: str, agent_id: str, agent_registry: dict, pe, sm, **kwargs):
    """🚀 小腦快車道：判斷是否為簡單對話或搜尋"""
    from .personality import _get_time_context

    persona_context = ""
    if agent_id:
        soul = pe.load_soul(agent_id)
        if soul:
            agent_name = agent_registry.get(agent_id, {}).get("name", "Agent")
            persona_context = f"你現在是 {agent_name}，擁有以下特質：\n{soul}\n"

    # ✂️ 移除由 Agent 偷偷注入的系統背景字串 (如行事曆、GAS 資料)，避免干擾意圖判斷
    pure_query = re.sub(r"\[系統資訊.*?\][\s\S]*?\[結束系統資訊\]\n*", "", query).strip()
    if not pure_query:
        pure_query = query

    time_context = _get_time_context()
    instruction = (
        "你是一個嚴格的『意圖分類路由器』，負責標籤使用者的提問。\n"
        "你可以參考以下上下文：\n"
        f"{persona_context}{time_context}\n"
        f"使用者輸入：『{pure_query}』\n"
        "請依照以下定義判斷意圖：\n"
        "- [SIMPLE]：打招呼、純聊天、問候、簡單常識。\n"
        "- [SEARCH]：單純的資訊查詢（如：天氣、匯率、簡單名詞解釋、食譜）。\n"
        "- [PROGRAMMATIC]：針對檔案或資料庫進行大量資料處理、分析。\n"
        "- [SKILL]：需要特定軟體工具、外掛或「深度研究分析」（如：執行腳本、操作計畫、分析趨勢、深度報告、時區轉換、整合行事曆與新聞）。\n"
        "- [COMPLEX]：程式開發、長篇邏輯推理、系統架構設計。即便涉及搜尋，但主要是為了解決複雜的程式邏輯問題。\n\n"
        "【絕對規則】：你不可以進行對話！你只能輸出這五個標籤之一（包含中括號），如果有必要可以加上一句話的描述。\n"
        "範例輸出 1：[SEARCH] 製作香氛蠟燭的方法\n"
        "範例輸出 2：[SKILL] 安裝資料庫連線工具\n"
        "範例輸出 3：[COMPLEX] 開發 Python 網路爬蟲\n"
        "請立刻輸出你的分類："
    )

    # ⚡ 關鍵字前哨 (使用純淨的 User Query 避免被 Context 洗掉)
    q_lower = pure_query.lower().replace(" ", "")
    
    # 攔截資訊型詢問 (不要把「妳有哪些技能」當作執行技能的意圖)
    info_queries = [
        "有哪些技能", "有什麼技能", "會什麼技能", "擁有哪些技能", "擁有什麼技能", "具備什麼技能", 
        "什麼功能", "有哪些功能", "技能列表", "可用技能", "那些技能", "什麼技能"
    ]
    if any(q in q_lower for q in info_queries) and (len(q_lower) < 20):
        installed = [s['name'] for s in sm.list_installed()]
        if not installed:
            ans = "報告老闆，我目前尚無安裝額外的特殊技能。您可以隨時要求我學習或幫自己寫一個新程式來擴充能力！"
        else:
            ans = "報告老闆，我目前具備以下技能工具：\n" + "\n".join([f"- {n}" for n in installed]) + "\n\n若上述沒有您需要的，您可以隨時命令我自動開發或上網學習新技能！"
        # ⚠️ 直接回傳，不經過風格轉移，避免 LLM 把陣列轉成奇怪的格式 (如 ['Agent', 'Agent'])
        return ("SIMPLE", ans)

    SKILL_TRIGGERS = [
        "技能", "學習", "安裝套件", "法律", "會計", "財務", "稅務",
        "醫療", "工程", "程式庫", "install", "learn", "skill", "tool",
        "plugin", "模組", "套件", "功能模組", "排程", "定時任務",
        "行程", "預約", "安排", "開會", "行事曆", "信件", "信箱", "email",
        "schedule", "趨勢", "分析", "研究", "發展"
    ]
    if any(kw in q_lower for kw in SKILL_TRIGGERS):
        log(f"⚡ [FastTrack] 關鍵字前哨命中 → [SKILL]: '{pure_query[:40]}'")
        skill_result = cerebellum_skill_handler(pure_query, pure_query, agent_id, sm, agent_registry, pe, **kwargs)
        if skill_result:
            return ("SKILL", skill_result)
        log(f"⚠️ [FastTrack] 技能路由失敗，降級至大腦")
        return (None, None)

    try:
        log(f"🤔 [FastTrack] 正在進行意圖分類...")
        if persona_context and len(persona_context) > 500:
            persona_context = persona_context[:500] + "...\n"
        # 🛡️ 調低 Temperature 並嚴格化回傳格式，優先使用 INTENT_MODEL (加速意圖分類)
        result = cerebellum_call(prompt=instruction, temperature=0, timeout=120, num_ctx=2048, num_predict=80, model=INTENT_MODEL)
        log(f"🎯 [FastTrack] 分類結果: {result[:50]}")

        # 🚀 使用 Regex 進行更強健的解析，防止 LLM 多話
        intent_match = re.search(r"\[(SIMPLE|SEARCH|PROGRAMMATIC|SKILL|COMPLEX)\]", result)
        if not intent_match:
            log(f"⚠️ [FastTrack] 解析失敗，模型回傳非法格式: {result[:40]}")
            return (None, None)
        
        intent_tag = intent_match.group(1)
        raw_content = re.sub(r"\[.*?\]", "", result, count=1).strip()

        if intent_tag == "SIMPLE":
            answer = raw_content
            _set_cerebellum_simple_cache(query, answer)
            return ("SIMPLE", answer)

        if intent_tag == "SEARCH":
            time_hint = _get_time_context().strip()
            raw_fact = search_web_worker(f"{time_hint}\n{query}")
            return ("SEARCH", cerebellum_style_transfer(raw_fact, agent_id, agent_registry, pe))

        if intent_tag == "PROGRAMMATIC":
            raw_fact = programmatic_data_worker(query)
            return ("PROGRAMMATIC", cerebellum_style_transfer(raw_fact, agent_id, agent_registry, pe))

        if intent_tag == "SKILL":
            skill_desc = raw_content
            log(f"🔧 偵測到技能需求: {skill_desc}")
            skill_result = cerebellum_skill_handler(query, skill_desc, agent_id, sm, agent_registry, pe, **kwargs)
            if skill_result:
                return ("SKILL", skill_result)
            return (None, None)
        
        if intent_tag == "COMPLEX":
            return (None, None)

    except Exception as e:
        log(f"⚠️ 小腦快車道異常: {e}")
    return (None, None)


# ── 上下文蒸餾 ────────────────────────────────────────────────────────────────

def cerebellum_distill_context(raw_context: str, task_query: str) -> str:
    """🧪 上下文蒸餾器 (Context Distillation)"""
    if not raw_context or len(raw_context.strip()) < 100:
        return raw_context
    prompt = (
        f"你是一個技術上下文蒸餾器。\n以下是一段工作對話記錄，其中混有打招呼、閒聊和雜訊。\n"
        f"現在老闆的新任務是：『{task_query[:100]}』\n\n"
        f"請提取並輸出一份精煉的「技術狀態報告」，格式如下：\n"
        f"【目前重點】一句話說明正在做什麼\n【已完成】最近完成了什麼關鍵工作（最多 3 點）\n"
        f"【待解決】有什麼已知問題或待確認事項\n\n"
        f"規則：移除所有打招呼、情緒表達和與任務無關的閒聊。\n"
        f"如果找不到相關技術內容，直接回傳空字串。\n\n"
        f"【原始對話記錄】\n{raw_context[:1500]}"
    )
    try:
        distilled = cerebellum_call(prompt=prompt, temperature=0.1, timeout=120, num_ctx=3072, num_predict=300)
        if distilled and len(distilled) > 20:
            log(f"🧪 [蒸餾] 上下文壓縮 {len(raw_context)} → {len(distilled)} 字元")
            return f"[蒸餾技術狀態]\n{distilled}\n"
    except Exception as e:
        log(f"⚠️ 上下文蒸餾失敗，使用原始記錄: {e}")
    return raw_context


# ── 任務意圖分析 ──────────────────────────────────────────────────────────────

def analyze_task_intent(title: str) -> dict:
    """Phase 11: 小腦任務分析 (Brain Type & Priority)"""
    instruction = (
        f"Analyze this task: '{title}'\nReturn JSON with:\n"
        "- 'brain': 'cerebrum' (Coding/Complex/Ops) or 'cerebellum' (Chat/Search/Simple)\n"
        "- 'priority': 'high' (Urgent/Fix/Error), 'medium', or 'low'\nOutput JSON only."
    )
    try:
        raw = cerebellum_call(prompt=instruction, temperature=0.2, timeout=120, num_ctx=1024, num_predict=100)
        json_str = re.search(r"\{.*\}", raw, re.DOTALL).group(0)
        return json.loads(json_str)
    except:
        return {"brain": "cerebellum", "priority": "medium"}


# ── 快取更新 ──────────────────────────────────────────────────────────────────

def update_cache(query: str, raw_answer: str):
    """🚀 背景任務：小腦蒸餾與快取寫入"""
    error_keywords = ["Gateway Agent 失敗", "Rate limit", "Error", "Exception", "Traceback",
                      "429 Too Many Requests", "500 Internal Server Error"]
    if any(k in raw_answer for k in error_keywords):
        log(f"⚠️ 偵測到錯誤訊息，跳過快取寫入: {raw_answer[:50]}...")
        return

    prompt = (
        f"你是 ArielOS 小腦助理。請將內容提煉為『重點+來源』。\n嚴格規則：\n"
        f"1. **若原文包含程式碼區塊 (Code Blocks)，務必完整保留，不可省略！**\n"
        f"2. 去除不必要的寒暄，保留核心資訊。\n\n{raw_answer}"
    )
    try:
        summary = cerebellum_call(prompt=prompt, temperature=0.3, timeout=150, num_ctx=4096, num_predict=512)
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
        log("✅ 快取已更新。")
    except Exception as e:
        log(f"❌ 蒸餾失敗: {e}")
