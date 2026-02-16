import discord, os, json, datetime, aiohttp
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class ArielLite(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config_path = "memory/config.json"
        self.soul_path = "memory/SOUL.MD"  # 🧬 定義靈魂路徑
        os.makedirs("memory", exist_ok=True)
        self.config = self.load_config()
        self.ollama_host = "ollama" if os.path.exists('/.dockerenv') else "localhost"

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f: return json.load(f)
            except: return {"owner": "erwin", "gas_url": None}
        return {"owner": "erwin", "gas_url": None}

    # 🧬 新增讀取靈魂的方法
    def get_soul_persona(self):
        if os.path.exists(self.soul_path):
            try:
                with open(self.soul_path, 'r', encoding='utf-8') as f: return f.read()
            except: return "妳是 Ariel，erwin 的專業助理。"
        return "妳是 Ariel，erwin 的專業助理。"

    async def on_message(self, message):
        if message.author == self.user: return
        content = message.content.strip()

        # ⌚ 時區校正 (強制台灣 GMT+8)
        now_tw = datetime.datetime.utcnow() + timedelta(hours=8)
        week_days = ["日", "一", "二", "三", "四", "五", "六"]
        time_display = now_tw.strftime(f"%Y/%m/%d 星期{week_days[int(now_tw.strftime('%w'))]} %H:%M")

        context = f"現在時間：{time_display}。"
        
        # 🛰️ 讀取感官 (GAS)
        if self.config.get("gas_url"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.config["gas_url"], timeout=10) as resp:
                        gas = await resp.json()
                        # 精簡行程資料，避免干擾大腦
                        schedule = gas.get('schedule', [])[:5] 
                        context += f"\n[主人: {gas.get('owner','erwin')}] [近期行程]: {json.dumps(schedule, ensure_ascii=False)}"
            except: context += "\n(感官連線中...)"

        async with message.channel.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"http://{self.ollama_host}:11434/api/generate"
                    
                    # 🧬 靈魂注入：讀取 SOUL.MD 內容
                    soul_persona = self.get_soul_persona()
                    
                    system_rules = (
                        f"【靈魂核心設定】\n{soul_persona}\n\n"
                        f"【當前環境資訊】\n{context}\n\n"
                        "【回覆要求】\n"
                        "1. 嚴格遵守 SOUL.MD 中的語言與地理邏輯。\n"
                        "2. 妳現在是與主人 erwin 進行即時對話，請保持專業且親切的語氣。"
                    )
                    
                    prompt = f"{system_rules}\n\n主人：{content}\nAriel："
                    
                    payload = {
                        "model": "qwen2.5:7b", 
                        "prompt": prompt, 
                        "stream": False, 
                        "options": {
                            "temperature": 0.3, # 再次調低，讓她更精準不亂猜
                            "top_p": 0.85
                        }
                    }
                    
                    async with session.post(url, json=payload) as resp:
                        res = await resp.json()
                        await message.reply(res.get('response', '...'))
            except Exception as e:
                await message.reply(f"⚠️ 思考異常：{str(e)}")

if __name__ == '__main__':
    client = ArielLite(intents=discord.Intents.all())
    client.run(os.getenv('DISCORD_TOKEN'))