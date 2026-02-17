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
        
        # 🌐 分散式設定：優先讀取環境變數，保護隱私
        self.remote_ip = os.getenv("REMOTE_BRAIN_IP") 
        self.bridge_url = f"http://{self.remote_ip}:28888/v1/chat/completions" if self.remote_ip else None
        
        # 🧠 大小腦模型定義
        self.local_brain = os.getenv("LOCAL_MODEL", "qwen2.5:0.5b")
        self.remote_brain = os.getenv("REMOTE_MODEL", "qwen2.5:7b")
        
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
        now_tw = datetime.datetime.utcnow() + timedelta(hours=8)
        context = f"現在時間：{now_tw.strftime('%Y/%m/%d %H:%M')}。"

        # 🛰️ 感官同步 (GAS)
        if self.config.get("gas_url"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.config["gas_url"], timeout=5) as resp:
                        gas = await resp.json()
                        context += f"\n[主人行程]: {json.dumps(gas.get('schedule', [])[:3], ensure_ascii=False)}"
            except: context += "\n(感官同步中...)"

        async with message.channel.typing():
            try:
                # 🧠 智慧派送判斷 (判斷標準：長度或複雜關鍵字)
                is_complex = len(content) > 40 or any(k in content for k in ["分析", "寫", "程式", "為什麼"])
                soul = self.get_soul_persona()
                sys_prompt = f"{soul}\n\n{context}\n\n請以繁體中文回答。"

                async with aiohttp.ClientSession() as session:
                    # 如果需要大腦且遠端 IP 已設定
                    if is_complex and self.bridge_url:
                        payload = {
                            "model": self.remote_brain,
                            "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": content}]
                        }
                        async with session.post(self.bridge_url, json=payload, timeout=60) as resp:
                            res = await resp.json()
                            answer = res.get('choices', [{}])[0].get('message', {}).get('content', '大腦未回應')
                            source = "🌐 [Remote Brain]"
                    else:
                        payload = {
                            "model": self.local_brain,
                            "prompt": f"{sys_prompt}\n\n主人：{content}\nAriel：",
                            "stream": False
                        }
                        async with session.post(self.local_url, json=payload, timeout=30) as resp:
                            res = await resp.json()
                            answer = res.get('response', '...')
                            source = "⚡ [Local Cerebellum]"

                    await message.reply(f"{answer}\n\n{source}")
            except Exception as e:
                await message.reply(f"⚠️ 思考異常：{str(e)}")

if __name__ == '__main__':
    client = ArielLite(intents=discord.Intents.all())
    client.run(os.getenv('ARIEL_NODE_TOKEN'))
