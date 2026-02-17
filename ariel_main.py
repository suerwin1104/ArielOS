import discord, os, json, datetime, aiohttp
from datetime import timedelta
from dotenv import load_dotenv

# 載入 .env 檔案（請確保裡面有 S9_BOT_TOKEN）
load_dotenv()

class ArielS9Bot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config_path = "memory/config.json"
        self.soul_path = "memory/SOUL.MD"
        os.makedirs("memory", exist_ok=True)
        self.config = self.load_config()
        
        # 🌐 網路路徑設定 (分散式核心)
        self.win11_ip = "100.110.201.24"     # Win11 的 Tailscale IP
        self.bridge_port = "28888"           # 橋接器 Port
        self.local_ollama = "http://localhost:11434/api/generate"
        self.remote_bridge = f"http://{self.win11_ip}:{self.bridge_port}/v1/chat/completions"
        
        # 🧠 大腦模型設定
        self.local_brain = "qwen2.5:0.5b"    # S9 輕量小腦
        self.remote_brain = "qwen2.5:7b"     # Win11 強大大腦

    def load_config(self):
        """讀取基礎配置與 GAS URL"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f: return json.load(f)
            except: return {"owner": "erwin", "gas_url": None}
        return {"owner": "erwin", "gas_url": None}

    def get_soul_persona(self):
        """注入靈魂設定"""
        if os.path.exists(self.soul_path):
            try:
                with open(self.soul_path, 'r', encoding='utf-8') as f: return f.read()
            except: return "妳是 Ariel S9，主人 erwin 的貼身分機。"
        return "妳是 Ariel S9，主人 erwin 的貼身分機。"

    async def on_message(self, message):
        if message.author == self.user: return
        content = message.content.strip()

        # ⌚ 時區與環境校正 (GMT+8)
        now_tw = datetime.datetime.utcnow() + timedelta(hours=8)
        time_display = now_tw.strftime("%Y/%m/%d %H:%M")
        context_info = f"現在時間：{time_display}。"

        # 🛰️ 感官數據同步 (GAS)
        gas_context = ""
        if self.config.get("gas_url"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.config["gas_url"], timeout=5) as resp:
                        gas = await resp.json()
                        schedule = gas.get('schedule', [])[:3]
                        gas_context = f"\n[目前行程]: {json.dumps(schedule, ensure_ascii=False)}"
            except:
                gas_context = "\n(GAS 同步中...)"

        async with message.channel.typing():
            try:
                # 🧠 任務分流判斷 (簡單/短文 vs 複雜/長文)
                is_complex = len(content) > 40 or any(k in content for k in ["分析", "寫", "教我", "為什麼"])
                
                soul_persona = self.get_soul_persona()
                system_prompt = f"{soul_persona}\n{context_info}{gas_context}\n請用繁體中文回覆。"

                async with aiohttp.ClientSession() as session:
                    if is_complex:
                        # 📡 透過 Tailscale 呼叫 Win11 橋接器
                        payload = {
                            "model": self.remote_brain,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": content}
                            ]
                        }
                        async with session.post(self.remote_bridge, json=payload, timeout=60) as resp:
                            res = await resp.json()
                            # 支援 OpenAI 格式的回傳解析
                            answer = res.get('choices', [{}])[0].get('message', {}).get('content', '大腦回應解析失敗')
                            source = "🧠(Win11)"
                    else:
                        # 📱 本地 S9 輕量小腦處理
                        payload = {
                            "model": self.local_brain,
                            "prompt": f"{system_prompt}\n\n主人：{content}\nAriel：",
                            "stream": False
                        }
                        async with session.post(self.local_ollama, json=payload, timeout=30) as resp:
                            res = await resp.json()
                            answer = res.get('response', '...')
                            source = "⚡(S9)"

                    await message.reply(f"{answer}\n\n來源: {source}")

            except Exception as e:
                await message.reply(f"⚠️ 系統異常：{str(e)}")

if __name__ == '__main__':
    # 啟動機器人
    client = ArielS9Bot(intents=discord.Intents.all())
    client.run(os.getenv('S9_BOT_TOKEN'))
