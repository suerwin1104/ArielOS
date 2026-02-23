import requests
import json
import datetime

OLLAMA_API = "http://127.0.0.1:11434/api/generate"

def _get_time_context():
    now = datetime.datetime.now()
    weekday = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
    return f"[系統時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (星期{weekday})]\n"

def test_intent():
    query = "學會會計技能(Accounting Skills)"
    
    # Replicate the prompt from ariel_bridge.py
    persona_context = ""
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

    print(f"Testing Query: {query}")
    try:
        resp = requests.post(OLLAMA_API, json={
            "model": "gemma3:4b", 
            "prompt": instruction, 
            "stream": False,
            "options": {"temperature": 0.3}
        }, timeout=60).json()
        
        result = resp.get('response', '').strip()
        print(f"LLM Result: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_intent()
