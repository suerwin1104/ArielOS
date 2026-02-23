import sys
from pathlib import Path

# Add modules to path
sys.path.append(str(Path(r'c:\Users\USER\Ariel_System\Central_Bridge')))

from modules.cerebellum import search_web_worker

def test_google_ai():
    query = "如何DIY廚房清潔液?"
    print(f"Testing hybrid search for query: {query}")
    result = search_web_worker(query)
    print("\nSearch Result:")
    print("-" * 30)
    print(result)
    print("-" * 30)

if __name__ == "__main__":
    test_google_ai()
