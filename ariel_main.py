import discord, os, aiohttp, datetime
from dotenv import load_dotenv

load_dotenv()

class ArielAgent(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 指向總部 IP
        self.bridge_url = f"http://{os.getenv('REMOTE_BRAIN_IP', '100.110.201.24')}:28888/v1/chat/completions"

    async def on_message(self, message):
        if message.author == self.user: return
        
        async with message.channel.typing():
            try:
                # 1. 讀取本分身專屬靈魂
                soul = ""
                if os.path.exists("memory/SOUL.MD"):
                    with open("memory/SOUL.MD", "r", encoding="utf-8") as f: soul = f.read()

                # 2. 自動取得當前時間 (確保大腦知道現在幾點)
                now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                time_ctx = f"現在時間：{now}"

                # 3. 傳送至總部
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "soul": soul,
                        "time_context": time_ctx,
                        "messages": [{"role": "user", "content": message.content}]
                    }
                    async with session.post(self.bridge_url, json=payload, timeout=120) as resp:
                        res = await resp.json()
                        await message.reply(res.get('choices', [{}])[0].get('message', {}).get('content', '...'))
            except Exception as e:
                await message.reply(f"⚠️ 無法聯繫總部：{str(e)}")

if __name__ == '__main__':
    client = ArielAgent(intents=discord.Intents.all())
    client.run(os.getenv('DISCORD_TOKEN'))
