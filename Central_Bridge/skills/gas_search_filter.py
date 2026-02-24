import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import os
import json
import urllib.request
import re

def main():
    if len(sys.argv) < 2:
        print("❌ 缺少需求參數。")
        sys.exit(1)

    demand = sys.argv[1]
    gas_url = os.environ.get("GAS_URL")

    if not gas_url:
        print("⚠️ 無法執行此技能：您的個人設定檔 (SOUL.md) 中尚未設定 GAS_URL。")
        sys.exit(1)

    # 1. LLM-based Complex Demand Detection
    # Using the local Cerebellum model to intelligently parse the demand into JSON
    import requests
    OLLAMA_API = "http://127.0.0.1:11434/api/generate"
    CEREBELLUM_MODEL = "gemma3:4b-it-q4_K_M"

    instruction = f"""
    分析使用者需求，選擇最合適的「感官引擎 (Sensory Engine)」：
    
    【感官路由規則】
    1. 🎯 [精確調校] - 針對：硬體規格、特定版本號、Bug 修補、GitHub/Reddit 討論、官方文件。
       ⮕ 輸出：{{"action": "search", "params": {{"query": "精簡關鍵字", "searchType": "google", "filterCode": "data = data"}}}}
    
    2. 🧠 [開放研究] - 針對：趨勢分析、未來預測、長篇報告、新聞懶人包、多方觀點。
       ⮕ 輸出：{{"action": "search", "params": {{"query": "精簡核心詞", "searchType": "exa", "filterCode": "data = data"}}}}
    
    3. ⚡ [簡單事實] - 針對：今日日期、天氣、簡單定義、匯率。
       ⮕ 輸出：{{"action": "local_search", "query": "關鍵字"}}
    
    4. 🔍 [深度探針] - 針對：明確要求「深度搜尋」、「截圖分析」、「PDF全文」或網頁被封鎖。
       ⮕ 輸出：{{"action": "search_deep", "query": "完整需求"}}
       
    【語言與區域規則】
    - 所有搜尋結果必須以「繁體中文」為主。
    - 優先考慮「台灣」或「全球」觀點，除非使用者明確要求「中國大陸」。
    - 在搜尋關鍵字 (query) 中，若無明確區域，可適度加入「台灣」或「繁體」等詞彙以優化結果。
    
    可用任務：calendar(天數), emails(數量), search(GA-引擎), local_search(簡單), search_deep(探針)。
    
    使用者需求：『{demand}』
    
    請回傳 JSON 陣列。注意：search 的 query 必須精簡。僅回傳 JSON，不要 markdown。
    """

    tasks = []
    _log(f"🧠 正在請求調度員 (Dispatcher) 分析感官層級...")
    try:
        resp = requests.post(OLLAMA_API, json={
            "prompt": instruction,
            "model": CEREBELLUM_MODEL,
            "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 1024}
        }, timeout=120)
        llm_output = resp.json().get('response', '').strip()
        
        json_match = re.search(r'\[.*\]', llm_output, re.DOTALL)
        if json_match:
            tasks = json.loads(json_match.group(0))
            _log(f"⚖️ 調度員決策: {json.dumps(tasks, ensure_ascii=False)}")
        else:
            _log(f"⚠️ 調度解析失敗，退回預設搜尋模式。")
    except Exception as e:
        _log(f"⚠️ 小腦連線失敗 ({e})。")

    # 處理任務分流與執行
    if not tasks:
        tasks = [{"action": "search", "params": {"query": demand, "searchType": "exa"}}]

    print(f"**[ArielOS 感官路由決策報告]**\n")
    
    batch_gas_tasks = []
    for t in tasks:
        action = t.get("action")
        if action in ["calendar", "emails", "search"]:
            batch_gas_tasks.append(t)
        elif action == "local_search":
            _log(f"⚡ 執行本地快速檢索: {t.get('query')}")
            # Here we just print instructions as it's a bridge between skills
            print(f"> [本地搜尋] 請參考本地資訊來源處理: {t.get('query')}\n")
        elif action == "search_deep":
            _log(f"🔍 啟動深度探針 (Playwright)...")
            print(f"> [深度探針] 正在喚醒本地瀏覽器進行精準掃描...\n")

    if batch_gas_tasks:
        payload = {"action": "batch_execute", "tasks": batch_gas_tasks}
        _log(f"📡 傳送 {len(batch_gas_tasks)} 個雲端蒸餾任務至 GAS...")
        
        try:
            req = urllib.request.Request(gas_url, data=json.dumps(payload).encode('utf-8'),
                                        headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=45) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get("status") == "success":
                    data = result.get("data", {})
                    # ... (Display outputs for calendar, emails, search)
                    display_gas_results(data)
                else:
                    print(f"❌ GAS 執行失敗: {result.get('error')}")
        except Exception as e:
            print(f"❌ 通訊異常: {e}")

def display_gas_results(data):
    if "calendar" in data:
        print(f"📅 **近期行程:**")
        for s in data["calendar"]: print(f"- {s['time']} {s['title']}")
        print()
    if "emails" in data:
        print(f"📧 **新進信件 (已蒸餾):**")
        for e in data["emails"]: print(f"- From: {e['from']}\n  Subject: {e['subject']}\n  Snippet: {e['snippet']}...")
        print()
    if "search" in data:
        res = data["search"]
        engine = "Exa 語義" if res.get("params", {}).get("searchType") == "exa" else "Google 精確"
        print(f"🔍 **{engine} 引擎結果 ({res.get('query')}):**")
        for item in res.get("result", []):
            if isinstance(item, dict):
                print(f"- **{item.get('title')}**\n  {item.get('content', '')[:200]}...\n  Link: {item.get('url')}\n")
            else: print(f"- {item}")

def _log(msg):
    print(f"🔧 [Sensory-Router] {msg}")

if __name__ == "__main__":
    main()
