import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

from Central_Bridge.modules.cerebellum import programmatic_data_worker, cerebellum_fast_track_check

print("--- Testing Programmatic Worker directly ---")
query = "請從字串 'Apple 100, Banana 50, Orange 120, Grape 80' 中過濾出大於 90 的水果並排序印出"
result = programmatic_data_worker(query)
print(result)

print("\n--- Testing Fast Track Check Intent ---")
intent, result_ft = cerebellum_fast_track_check(
    query, 
    agent_id=None, 
    agent_registry={}, 
    pe=None, 
    sm=None  # We don't have skill manager initialized here, but it should hit PROGRAMMATIC
)
print("Intent:", intent)
print("Result:", result_ft)
