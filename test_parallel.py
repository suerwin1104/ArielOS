import requests, threading, time, json

BRIDGE_URL = "http://127.0.0.1:28888/v1/chat/completions"

def send_complex(agent_id, query):
    print(f"[{agent_id}] Sending COMPLEX: {query}")
    start = time.time()
    try:
        resp = requests.post(BRIDGE_URL, json={
            "messages": [{"role": "user", "content": query}],
            "agent_id": agent_id
        })
        print(f"[{agent_id}] Response Status: {resp.status_code}")
        if resp.status_code == 202:
            data = resp.json()
            tid = data['task_id']
            print(f"[{agent_id}] Queued Task ID: {tid}")
            # Poll
            while True:
                time.sleep(1)
                poll = requests.get(f"http://127.0.0.1:28888/v1/task/{tid}").json()
                if poll['status'] == 'completed':
                    end = time.time()
                    print(f"[{agent_id}] Finished in {end-start:.2f}s. Result: {poll['result'][:50]}...")
                    break
        else:
            end = time.time()
            print(f"[{agent_id}] Immediate Response? {resp.json()}")
    except Exception as e:
        print(f"[{agent_id}] Error: {e}")

def send_simple(agent_id, query):
    print(f"[{agent_id}] Sending SIMPLE: {query}")
    start = time.time()
    try:
        resp = requests.post(BRIDGE_URL, json={
            "messages": [{"role": "user", "content": query}],
            "agent_id": agent_id
        })
        end = time.time()
        print(f"[{agent_id}] Finished in {end-start:.2f}s. Response: {resp.json()['choices'][0]['message']['content'][:50]}...")
    except Exception as e:
        print(f"[{agent_id}] Error: {e}")

if __name__ == "__main__":
    # Agent 1 asks slow complex code (Write Python Script)
    t1 = threading.Thread(target=send_complex, args=("agent1", "寫一個 Python 腳本計算 1000 的階乘"))
    
    # Agent 2 asks fast simple chat (Hello)
    t2 = threading.Thread(target=send_simple, args=("agent2", "早安"))
    
    t1.start()
    time.sleep(0.5) # Slight delay
    t2.start()
    
    t1.join()
    t2.join()
