import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import os
import json
import urllib.request
import re
from datetime import datetime

from datetime import datetime, timedelta

def parse_event_details(query):
    """
    Improved heuristic parser for event details.
    """
    query = query.replace("Jessie", "").replace("Mandy", "").replace("幫我", "").strip()
    
    # 1. Date Detection (Today/Tomorrow)
    target_date = datetime.now()
    if "明天" in query:
        target_date += timedelta(days=1)
    elif "後天" in query:
        target_date += timedelta(days=2)
    elif "昨天" in query:
        target_date -= timedelta(days=1)

    # 2. Time Detection (HH:MM or HH:MM AM/PM)
    # Match HH:MM
    time_match = re.search(r'([0-9]|1[0-9]|2[0-3]):([0-5][0-9])', query)
    start_time_str = ""
    
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        
        # Handle AM/PM
        if "PM" in query.upper() or "下午" in query or "晚上" in query:
            if hour < 12: hour += 12
        elif "AM" in query.upper() or "上午" in query:
            if hour == 12: hour = 0
            
        start_time_str = target_date.replace(hour=hour, minute=minute).strftime('%Y-%m-%d %H:%M')
    else:
        # Default to 09:00 if no time mentioned
        start_time_str = target_date.replace(hour=9, minute=0).strftime('%Y-%m-%d 09:00')

    # 3. Title Extraction
    # Remove metadata delimiters if present
    title = re.sub(r'內容[:：]', '', query)
    title = re.sub(r'時間[:：]', '', title)
    
    # Remove the matched time string and other noise
    if time_match:
        title = title.replace(time_match.group(0), "")
    
    for noise in ["加入行程", "新增行程", "明天", "後天", "昨天", "時間", "內容", "AM", "PM", "下午", "上午"]:
        title = title.replace(noise, "")
    
    title = title.replace(",", "").replace("，", "").replace("。", "").strip()
    if not title:
        title = "未命名行程"

    return title, start_time_str

def main():
    if len(sys.argv) < 2:
        print("❌ 缺少查詢參數。")
        sys.exit(1)

    query = sys.argv[1]
    gas_url = os.environ.get("GAS_URL")

    if not gas_url:
        print("⚠️ 無法執行此技能：您的個人設定檔 (SOUL.md) 中尚未設定 GAS_URL。")
        sys.exit(1)

    # 1. 寫入偵測 (預約/安排/新增/加入/登記/記錄)
    write_keywords = ["預約", "安排", "book", "新增", "加入", "登記", "記錄"]
    is_write = any(kw.lower() in query.lower() for kw in write_keywords)

    if is_write:
        title, start_time = parse_event_details(query)
        if not title or not start_time:
            # Tell the agent LLM to ask the user for more info
            print("⚠️ 資訊不完整，無法建立行程。請提供精確的標題與時間 (格式例如：明天下午三點開會)。")
            sys.exit(0)

        payload = {
            "action": "add",
            "title": title[:50],  # safety cap
            "startTime": start_time,
            "endTime": ""
        }
        
        try:
            req = urllib.request.Request(
                gas_url, 
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get("status") == "success":
                    print(f"✅ 行程預約成功！\n📅 時間：{start_time}\n📌 標題：{title}")
                else:
                    print(f"❌ 寫入失敗 (GAS 回應)：{result.get('error', '未知錯誤')}")
        except Exception as e:
            print(f"❌ 寫入失敗 (連線異常)：{e}")
        
        sys.exit(0)

    # 2. 讀取偵測 (查詢)
    try:
        req = urllib.request.Request(gas_url, method='GET')
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if data.get('status') == 'success':
                s_list = data.get('schedule', [])
                schedule_text = "\n".join([f"- {s['time']} {s['title']}" for s in s_list]) if s_list else "(目前無近期行程)"
                
                e_list = data.get('emails', [])
                email_text = "\n".join([f"- [{e['date']}] {e['subject']} (發件人: {e['from']})" for e in e_list]) if e_list else "(目前無未讀信件)"
                
                print(f"**[您的雲端行事曆與信箱摘要]**")
                print(f"📅 今日：{data.get('today', 'Unknown')}")
                print(f"\n📌 近期行程：\n{schedule_text}")
                print(f"\n📧 未讀信件：\n{email_text}")
            else:
                print(f"❌ 讀取失敗：GAS 服務端回報錯誤。")
    except Exception as e:
        print(f"❌ 讀取失敗 (連線異常)：{e}")

if __name__ == "__main__":
    main()
