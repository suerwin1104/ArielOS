import discord, os, aiohttp, json
from dotenv import load_dotenv

load_dotenv()

class ArielOS(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mem_dir = "memory"
        self.identity_file = f"{self.mem_dir}/IDENTITY.md"
        self.user_file = f"{self.mem_dir}/USER.md"
        os.makedirs(self.mem_dir, exist_ok=True)
        self.bridge_url = f"http://{os.getenv('REMOTE_BRAIN_IP', '100.110.201.24')}:28888/v1/chat/completions"

    def get_dynamic_soul(self):
        """從檔案讀取人格，若無則回傳預設初始化提示"""
        if not os.path.exists(self.identity_file) or not os.path.exists(self.user_file):
            return "系統尚未初始化。請引導用戶設定 AI 名稱與主人稱呼。"
        
        with open(self.identity_file, 'r', encoding='utf-8') as f: identity = f.read()
        with open(self.user_file, 'r', encoding='utf-8') as f: user = f.read()
        return f"【身分設定】\n{identity}\n\n【用戶資料】\n{user}"

    async def on_message(self, message):
        if message.author == self.user: return
        content = message.content.strip()

        async with message.channel.typing():
            soul = self.get_dynamic_soul()
            
            # 🚀 初始化儀式：如果用戶輸入「初始化」
            if "初始化" in content:
                await message.reply("🌟 啟動靈魂初始化儀式... 請告訴我：\n1. 您希望我叫什麼名字？\n2. 我該如何稱呼您？\n(範例：我是 Ariel，主人是 erwin)")
                return

            try:
                async with aiohttp.ClientSession() as session:
                    payload = {"soul": soul, "messages": [{"role": "user", "content": content}]}
                    async with session.post(self.bridge_url, json=payload, timeout=90) as resp:
                        res = await resp.json()
                        answer = res.get('choices', [{}])[0].get('message', {}).get('content', '...')
                        await message.reply(answer)
            except Exception as e:
                await message.reply(f"⚠️ 連線異常，請確認橋接器狀態。")

if __name__ == '__main__':
    client = ArielOS(intents=discord.Intents.all())
    client.run(os.getenv('DISCORD_TOKEN'))
