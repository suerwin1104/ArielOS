import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "Central_Bridge"))
from Central_Bridge.modules.cerebellum import search_web_worker

print("Testing search_web_worker...")
result = search_web_worker("台北現在天氣")
print("Raw API Output:", result)
