import sys
import os
import json

# Add Central_Bridge to path
sys.path.append(os.path.join(os.getcwd(), "Central_Bridge"))
from skill_manager import SkillManager

def test_search():
    base_dir = os.path.join(os.getcwd())
    sm = SkillManager(base_dir)
    
    # 測試中文查詢 (包含安裝意圖)
    query = "安裝 Python 會計套件"
    print(f"Testing search for: {query}")
    
    # search_skill_online should extract English terms -> "python accounting library" -> perform search
    candidates = sm.search_skill_online(query)
    
    print(f"\nFound {len(candidates)} candidates:")
    for c in candidates:
        print(f"- {c['name']} [{c['type']}]: {c['description'][:60]}...")
        if 'accounting' in c['name'].lower() or 'beancount' in c['name'].lower() or 'pandas' in c['name'].lower():
            print("  ✅ Match found!")
            
    if not candidates:
        print("\n❌ No candidates found.")
    else:
        print("\n✅ Search successful.")

if __name__ == "__main__":
    test_search()
