import requests
import time

API_URL = "http://127.0.0.1:28888/v1/team/dispatch"

def test_dispatch():
    print("🧪 Testing Dispatcher API...")
    
    # 1. Dispatch Commander to plan
    payload = {
        "role": "Commander",
        "payload": "Rule the world with Python"
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=120)
        print(f"Commander Response ({resp.status_code}):")
        print(resp.json())
    except Exception as e:
        print(f"❌ Commander failed: {e}")

    # 2. Dispatch Worker to code
    payload = {
        "role": "Worker",
        "payload": "Write a hello_world.py that prints 'Hello ArielOS'"
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=120)
        print(f"\nWorker Response ({resp.status_code}):")
        try:
            print(resp.json())
        except:
            print(f"⚠️ Raw Response: {resp.text}")
    except Exception as e:
        print(f"❌ Worker failed: {e}")

    # 3. Dispatch Reviewer to check
    # 注意：這裡假設 Task ID 是一致的，但在測試中我們每次都生成新的 Task ID。
    # 為了模擬真實情境，Reviewer 應該要能讀取 Worker 的工作區。
    # 這裡我們先測試 Dispatcher 是否能喚起 Reviewer。
    payload = {
        "role": "Reviewer",
        "payload": "Review the code in workspace/task_latest/hello_world.py"
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=120)
        print(f"\nReviewer Response ({resp.status_code}):")
        try:
            print(resp.json())
        except:
             print(f"⚠️ Raw Response: {resp.text}")
    except Exception as e:
        print(f"❌ Reviewer failed: {e}")

if __name__ == "__main__":
    test_dispatch()
