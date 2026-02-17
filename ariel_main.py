import discord, os, aiohttp, datetime
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class ArielOS(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mem_dir = "memory"
        self.soul_file = f"{self.mem_dir}/SOUL.MD"
        self.user_file = f"{self.mem_dir}/USER.MD"
        os.makedirs(self.mem_dir, exist_ok=True)
        # 預設連向本機橋接器，若在 Docker 執行可透過環境變數修改
        self.bridge_url = f"http://{os.getenv('REMOTE_BRAIN_IP', '127.0.0.1')}:28888/v1/chat/completions"

    def get_soul_context(self):
        """讀取本地人格檔。這是 AI 的靈魂核心，若檔案不存在則引導初始化"""
        soul_content = ""
        if os.path.exists(self.soul_file):
            with open(self.soul_file, 'r', encoding='utf-8') as f:
                soul_content += f"【夥伴性格與設定】\n{f.read()}\n"
        if os.path.exists(self.user_file):
            with open(self.user_file, 'r', encoding='utf-8') as f:
                soul_content += f"【主人(用戶)資料】\n{f.read()}\n"
        return soul_content if soul_content else "妳是一位專業的 AI 夥伴，目前尚未收到具體人格設定。"

    async def on_message(self, message):
        if message.author == self.user: return
        content = message.content.strip()

        # 🌟 靈魂初始化介面：讓任何人都能設定自己的夥伴
        if content == "初始化":
            await message.reply("🌟 **靈魂初始化儀式啟動**\n請分別輸入以下指令來設定：\n1. `設定夥伴：[名字], [性格特質]`\n2. `設定主人：[您的稱呼與喜好]`")
            return

        if content.startswith("設定夥伴："):
            info = content.replace("設定夥伴：", "")
            with open(self.soul_file, 'w', encoding='utf-8') as f: f.write(info)
            await message.reply(f"✅ 夥伴靈魂已更新：{info}")
            return

        if content.startswith("設定主人："):
            info = content.replace("設定主人：", "")
            with open(self.user_file, 'w', encoding='utf-8') as f: f.write(info)
            await message.reply(f"✅ 主人資料已更新：{info}")
            return

        # 環境感知 (時間資訊)
        now_tw = datetime.datetime.utcnow() + timedelta(hours=8)
        time_ctx = f"現在時間：{now_tw.strftime('%Y/%m/%d %H:%M')}。"

        async with message.channel.typing():
            try:
                soul = self.get_soul_context()
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "soul": soul,
                        "time_context": time_ctx,
                        "messages": [{"role": "user", "content": content}]
                    }
                    async with session.post(self.bridge_url, json=payload, timeout=90) as resp:
                        res = await resp.json()
                        answer = res.get('choices', [{}])[0].get('message', {}).get('content', '...')
                        await message.reply(answer)
            except Exception as e:
                await message.reply(f"⚠️ 夥伴連線中斷，請確認橋接器是否開啟：{str(e)}")

if __name__ == '__main__':
    client = ArielOS(intents=discord.Intents.all())
    client.run(os.getenv('DISCORD_TOKEN'))
