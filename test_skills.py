"""
ArielOS Skills System Test Script
測試 Phase 13 技能路由與管理 API
前置條件：啟動 Bridge (python Central_Bridge/ariel_bridge.py)
"""

import requests, time, json

BASE = "http://127.0.0.1:28888"

def test_skills_api():
    """測試 Skills REST API"""
    print("=" * 50)
    print("🧪 Test 1: GET /v1/skills (列出技能)")
    print("=" * 50)
    try:
        resp = requests.get(f"{BASE}/v1/skills", timeout=10)
        data = resp.json()
        print(f"  Status: {resp.status_code}")
        print(f"  Catalog: {len(data.get('catalog', []))} 項")
        print(f"  Installed: {len(data.get('installed', []))} 項")
        for s in data.get('catalog', []):
            print(f"    📦 {s['name']}: {s['description']}")
    except Exception as e:
        print(f"  ❌ 錯誤: {e}")

    print()
    print("=" * 50)
    print("🧪 Test 2: POST /v1/skills/search (搜尋技能)")
    print("=" * 50)
    try:
        resp = requests.post(f"{BASE}/v1/skills/search", 
            json={"query": "filesystem 檔案操作"}, timeout=30)
        results = resp.json()
        print(f"  Status: {resp.status_code}")
        print(f"  Results: {len(results)} 項")
        for r in results:
            print(f"    🔍 {r.get('name')}: {r.get('description', '')[:50]}")
    except Exception as e:
        print(f"  ❌ 錯誤: {e}")


def test_skill_routing():
    """測試技能路由分類"""
    test_cases = [
        ("早安", "SIMPLE"),
        ("NVDA 股價多少", "SEARCH"),
        ("幫我讀取 README.md 的內容", "SKILL"),
        ("現在東京幾點", "SKILL"),
        ("寫一個 Python 排序演算法", "COMPLEX"),
    ]

    print()
    print("=" * 50)
    print("🧪 Test 3: 技能路由分類 (透過 chat API)")
    print("=" * 50)

    for query, expected in test_cases:
        print(f"\n  📝 測試: '{query}' (預期: {expected})")
        start = time.time()
        try:
            resp = requests.post(f"{BASE}/v1/chat/completions", json={
                "messages": [{"role": "user", "content": query}],
                "agent_id": "agent1"
            }, timeout=120)
            elapsed = time.time() - start
            
            if resp.status_code == 202:
                # 進入大腦佇列 = COMPLEX
                print(f"  → 結果: COMPLEX (202 Queued) | {elapsed:.1f}s")
            elif resp.status_code == 200:
                data = resp.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                route = "SIMPLE/SEARCH/SKILL"
                if "[技能:" in content:
                    route = "SKILL"
                elif "[網路搜尋" in content:
                    route = "SEARCH"
                else:
                    route = "SIMPLE"
                print(f"  → 結果: {route} (200) | {elapsed:.1f}s | 內容: {content[:60]}...")
        except Exception as e:
            print(f"  ❌ 錯誤: {e}")


if __name__ == "__main__":
    print("🚀 ArielOS Skills System Test")
    print(f"   Bridge: {BASE}")
    print()
    
    test_skills_api()
    test_skill_routing()
    
    print("\n✅ 測試完成")
