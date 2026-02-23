import sys, re
file_path = 'Central_Bridge/ariel_bridge.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('requests.post(', 'ollama_session.post(')
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

file_path2 = 'Central_Bridge/skill_manager.py'
with open(file_path2, 'r', encoding='utf-8') as f:
    content2 = f.read()
content2 = content2.replace('requests.post(', 'ollama_session.post(').replace('import requests', 'import requests\nollama_session = requests.Session()\nadapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=1)\nollama_session.mount(\'http://\', adapter)')
with open(file_path2, 'w', encoding='utf-8') as f:
    f.write(content2)

file_path3 = 'Central_Bridge/memory_manager.py'
with open(file_path3, 'r', encoding='utf-8') as f:
    content3 = f.read()
content3 = content3.replace('requests.post(', 'ollama_session.post(').replace('import requests', 'import requests\n        ollama_session = requests.Session()\n        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=1)\n        ollama_session.mount(\'http://\', adapter)')
with open(file_path3, 'w', encoding='utf-8') as f:
    f.write(content3)
print("Replacement complete.")
