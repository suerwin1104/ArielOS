# -*- coding: utf-8 -*-
import json
import sys
import os
import re
from pathlib import Path

# 從環境變數或預設路徑取得 BASE_DIR
BASE_DIR = Path(os.getenv("ARIEL_DIR", Path.home() / "Ariel_System"))
ROUTINES_PATH = BASE_DIR / "Shared_Vault" / "routines.json"

def load_routines():
    if not ROUTINES_PATH.exists():
        return {"routines": []}
    try:
        with open(ROUTINES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"routines": []}

def save_routines(data):
    ROUTINES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ROUTINES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def list_routines():
    data = load_routines()
    routines = data.get("routines", [])
    if not routines:
        return "📅 目前沒有設定任何例行任務。您可以命令我新增一個排程！"
    res = "📅 目前的例行任務列表：\n"
    for i, r in enumerate(routines):
        res += f"{i+1}. 🕒 [{r.get('time')}] ({r.get('agent_id')}): {r.get('task')}\n"
    res += "\n💡 若要刪除，請說：『刪除排程第 X 個』"
    return res

def add_routine(time_str, agent_id, task):
    data = load_routines()
    data["routines"].append({
        "time": time_str,
        "agent_id": agent_id,
        "task": task
    })
    # 按時間排序
    data["routines"].sort(key=lambda x: x["time"])
    save_routines(data)
    return f"✅ 已成功建立排程：每天 {time_str} 由 {agent_id} 執行任務『{task}』。"

def remove_routine(index_str):
    try:
        idx = int(re.search(r"\d+", index_str).group()) - 1
        data = load_routines()
        if 0 <= idx < len(data["routines"]):
            removed = data["routines"].pop(idx)
            save_routines(data)
            return f"🗑️ 已刪除排程：[{removed.get('time')}] {removed.get('task')}。"
        else:
            return "❌ 找不到該序號的排程。"
    except Exception as e:
        return f"❌ 刪除失敗：{e}"

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    
    # 邏輯分發
    if not query or any(k in query for k in ["列表", "清單", "查看", "有哪些"]):
        print(list_routines())
    elif "刪除" in query:
        print(remove_routine(query))
    else:
        # 嘗試解析時間、人名、任務
        time_match = re.search(r"(\d{1,2}[:：]\d{2})", query)
        agent_match = re.search(r"(Jessie|Mandy|Ariel|Mina|Sora)", query, re.I)
        # 抓取任務描述 (通常是冒號後或最後一部分)
        content_match = re.search(r"(任務|要做|執行)[：:]\s*(.*)", query)
        if not content_match:
            # 嘗試抓取引號內的內容
            content_match = re.search(r"『(.*)』", query)
            
        if time_match:
            t = time_match.group(1).replace("：", ":")
            h, m = t.split(":")
            t = f"{h.zfill(2)}:{m.zfill(2)}"
            
            name = agent_match.group(1) if agent_match else "Jessie"
            # 簡易 ID 對照
            aid_map = {"jessie": "AID_JESSIE_v4", "mandy": "AID_MANDY_v4", "ariel": "AID_ARIEL_v4"}
            aid = aid_map.get(name.lower(), "AID_JESSIE_v4")
            
            task = content_match.group(2 if len(content_match.groups()) > 1 else 1).strip() if content_match else query
            print(add_routine(t, aid, task))
        else:
            print("請告知要新增的排程內容。例如：『幫我新增一個 09:00 由 Jessie 執行的任務：早上好』")
