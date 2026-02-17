import discord, os, json, datetime, aiohttp
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class ArielLite(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config_path = "memory/config.json"
        self.soul_path = "memory/SOUL.MD"
        os.makedirs("memory", exist_ok=True)
        self.config = self.load_config()
        
        # 🌐 分散式大腦配置 (核心優勢：算力共享)
        # 透過 Tailscale 連向您的 Win11 橋接器
        self.remote_ip = os.getenv("REMOTE_BRAIN_IP", "100.110.201.24") 
        self.bridge_url = f"http://{self.remote_ip}:28888/v1/chat/completions"
        
        # 🧠 大小腦模型定義
        self.local_brain = os.getenv("LOCAL_MODEL", "qwen2.5:0.5b") # 終端小腦
        self.remote_brain = os.getenv("REMOTE_MODEL", "qwen2.5:7b") # 遠端大腦
        
        # 本地 Ollama 路徑識別
        self.ollama_host = "ollama" if os.path.exists('/.dockerenv') else "localhost"
        self.local_url = f"http://{self.ollama_host}:11434/api/generate"

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f: return json.load(f)
            except: return {"owner": "erwin", "gas_url": None}
        return {"owner": "erwin", "gas_url": None}

    def get_soul_persona(self):
        if os.path.exists(self.soul_path):
            try:
                with open(self.soul_path, 'r', encoding='utf-8') as f: return f.read()
            except: return "妳是 Ariel，主人 erwin 的全能助理。"
        return "妳是 Ariel，主人 erwin 的全能助理。"

    async def on_message(self, message):
        if message.author == self.user: return
        content = message.content.strip()

        # ⌚ 時區與環境感知
        now_tw = datetime.datetime.utcnow() + timedelta(hours=8)
        time_display = now_tw.strftime("%Y/%m/%d %H:%M")
        context = f"現在時間：{time_display}。"

        # 🛰️ 感官同步 (GAS)
        if self.config.get("gas_url"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.config["gas_url"], timeout=5) as resp:
                        gas = await resp.json()
                        schedule = gas.get('schedule', [])[:3]
                        context += f"\n[主人行程]: {json.dumps(schedule, ensure_ascii=False)}"
            except: context += "\n(感官同步中...)"

        async with message.channel.typing():
            try:
                # 🧠 大小腦判斷邏輯 (智慧派送)
                # 複雜任務(長文/分析/程式)轉發至大腦，簡單任務由終端小腦處理
                is_complex = len(content) > 40 or any(k in content for k in ["分析", "解釋", "寫", "程式", "為什麼"])
                
                soul_persona = self.get_soul_persona()
                system_rules = f"{soul_persona}\n\n{context}\n\n請以繁體中文親切回答。"
                
                async with aiohttp.ClientSession() as session:
                    if is_complex:
                        # 📡 透過橋接器共享 Win11 算力 (OpenAI 格式)
                        payload = {
                            "model": self.remote_brain,
                            "messages": [
                                {"role": "system", "content": system_rules},
                                {"role": "user", "content": content}
                            ],
                            "temperature": 0.4
                        }
                        async with session.post(self.bridge_url, json=payload, timeout=60) as resp:
                            res = await resp.json()
                            answer = res.get('choices', [{}])[0].get('message', {}).get('content', '大腦連線異常')
                            source = "🌐 [Remote Brain]"
                    else:
                        # ⚡ 終端本地小腦快速響應 (Ollama 格式)
                        payload = {
                            "model": self.local_brain,
                            "prompt": f"{system_rules}\n\n主人：{content}\nAriel：",
                            "stream": False,
                            "options": {"temperature": 0.3}
                        }
                        async with session.post(self.local_url, json=payload, timeout=30) as resp:
                            res = await resp.json()
                            answer = res.get('response', '...')
                            source = "⚡ [Local Cerebellum]"

                    await message.reply(f"{answer}\n\n{source}")
                    
            except Exception as e:
                await message.reply(f"⚠️ 思考異常：{str(e)}")

if __name__ == '__main__':
    # 支援不同節點使用不同的 Bot Token (例如 S9 與 N3 分開)
    token = os.getenv('ARIEL_NODE_TOKEN') or os.getenv('DISCORD_TOKEN')
    client = ArielLite(intents=discord.Intents.all())
    client.run(token)
