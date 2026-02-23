import sys
from pathlib import Path
import datetime

# Add the modules path to sys.path
sys.path.append(str(Path(r'c:\Users\USER\Ariel_System\Central_Bridge')))

from modules.personality import spinal_chord_reflex
from modules.personality import PE
from modules.personality import AGENT_REGISTRY, load_agent_registry
from skill_manager import SkillManager

# Mocking or using real instances
load_agent_registry()
sm = SkillManager(Path(r'c:\Users\USER\Ariel_System'))

def test_reflexes():
    test_cases = [
        ("你好", "问候"),
        ("現在時間", "時間"),
        ("明天幾號", "日期"),
        ("有哪些技能", "技能清單"),
        ("妳是誰", "介紹"),
        ("系統狀態", "狀態"),
    ]

    print("=== Testing Spinal Chord Reflexes ===")
    for query, label in test_cases:
        res = spinal_chord_reflex(query, "agent1", AGENT_REGISTRY, PE, sm)
        print(f"[{label}] Query: {query}")
        print(f"Response: {res}")
        print("-" * 20)

if __name__ == "__main__":
    test_reflexes()
