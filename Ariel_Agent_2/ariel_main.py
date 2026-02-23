import discord, os, aiohttp, datetime, re, asyncio, json, logging
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# 🤖 代理人身份識別 (自動從資料夾名稱偵測，無需手動修改)
# 規則：Ariel_Agent_1 → agent1, Ariel_Agent_3 → agent3，以此類推
AGENT_DIR = Path(__file__).resolve().parent
_dir_name = AGENT_DIR.name  # e.g. "Ariel_Agent_2"
import re as _re
_m = _re.search(r'[Aa]gent[_\-]?(\w+)$', _dir_name)
AGENT_ID = f"agent{_m.group(1).lower()}" if _m else "agent1"

class ArielAgentNode(discord.Client):
    def __init__(self, *args, agent_dir_override=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.bridge_url = "http://127.0.0.1:28888/v1/chat/completions"
        # 支援從啟動器傳入覆蓋目錄 (for ariel_launcher.py multi-agent mode)
        self.agent_dir = Path(agent_dir_override) if agent_dir_override else AGENT_DIR
        _m = _re.search(r'[Aa]gent[_\-]?(\w+)$', self.agent_dir.name)
        self.agent_id = f"agent{_m.group(1).lower()}" if _m else AGENT_ID
        self.seen_events = set()
        self.seen_emails = set()
        self.announce_channel = None
        self._load_soul()

    async def on_ready(self):
        print(f"✅ {self.user} is ready and listening!")
        self.loop.create_task(self.bg_check_gas())
        self.loop.create_task(self.bg_check_kanban())  # ✅ 同步 Agent_1：啟動看板監控
        print(f"🤖 [{self.name}] 初始化完成: Bridge={self.bridge_url} | ID={self.agent_id}")

    def _load_soul(self):
        """讀取靈魂設定"""
        soul_path = self.agent_dir / "memory" / "SOUL.md"
        self.name, self.title, self.call = "Ariel", "秘書", "老闆"
        self.check_interval = 30
        if soul_path.exists():
            with open(soul_path, "r", encoding="utf-8") as f:
                text = f.read()
                n = re.search(r"姓名.*?[：:]\s*(.*?)\n", text)
                if n: self.name = n.group(1).replace('*', '').strip()
                t = re.search(r"現職.*?[：:]\s*(.*?)\n", text)
                if t: self.title = t.group(1).split('的')[-1].replace('*', '').strip()
                c = re.search(r"稱呼您為.*?[「](.*?)[」]", text)
                if c: self.call = c.group(1).strip()
                # 寬鬆匹配: 處理 GAS\_URL, [url], <url> 等各種格式
                g = re.search(r"(?i)GAS.*URL.*?(https?://[^\s<>\"'()\[\]]+)", text)
                self.gas_url = g.group(1).strip() if g else None
                # 讀取巡邏頻率
                ci = re.search(r"巡邏頻率.*?[：:]\s*(\d+)", text)
                if ci: self.check_interval = int(ci.group(1))

        print(f"🧬 [{self.name}] 靈魂載入完成 (agent_id: {self.agent_id}) | GAS: {'✅' if self.gas_url else '❌'} | Interval: {self.check_interval}m")

    def polish(self, text):
        """清理終端代碼與報錯殘留"""
        text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|\[\??\d+[hlmcJH]', '', text)
        for p in ["Exec: pty", "failed:", "Command exited"]:
            if p in text: text = text.split(p)[0]
        return text.strip()

    async def fetch_gas_data(self):
        """讀取 Google Apps Script 資料"""
        if not self.gas_url: return None
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(self.gas_url) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            print(f"⚠️ GAS 讀取失敗: {e}")
        return None

    async def create_gas_event(self, event_data):
        """寫入 Google Apps Script (新增行程)"""
        if not self.gas_url: return None
        try:
            payload = {
                "action": "add",
                "title": event_data.get("title", "未命名行程"),
                "startTime": event_data.get("startTime"),
                "endTime": event_data.get("endTime")
            }
            async with aiohttp.ClientSession() as sess:
                async with sess.post(self.gas_url, json=payload) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            print(f"⚠️ GAS 寫入失敗: {e}")

        return None


    async def bg_check_kanban(self):
        """Phase 12: 看板任務執行 - 僅接受 Watcher 排程建立的 TODO 任務"""
        await self.wait_until_ready()
        print(f"📋 [{self.name}] 看板監控已啟動 (僅處理 TODO 狀態)")
        
        while not self.is_closed():
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as sess:
                    base_url = self.bridge_url.replace('/v1/chat/completions', '')
                    async with sess.get(f"{base_url}/v1/kanban/tasks") as resp:
                        if resp.status == 200:
                            tasks = await resp.json()
                            
                            # ⚠️ 只取 TODO 狀態的任務（Watcher 建立的排程任務）
                            # DOING 狀態 = brain_worker 正在處理中，不可重複觸發（cron 洪水根源）
                            my_jobs = [
                                t for t in tasks
                                if t.get('agent_id') == self.agent_id
                                and t.get('status') == 'todo'
                            ]
                            
                            for job in my_jobs:
                                tid = job['id']
                                title = job['title']
                                patch_url = f"{base_url}/v1/kanban/tasks/{tid}"
                                
                                # 先搶佔標記為 doing，防止其他 Agent 重複執行
                                await sess.patch(patch_url, json={"status": "doing"})
                                print(f"⚙️ [{self.name}] Watcher 任務啟動: {title}")
                                
                                payload = {
                                    "messages": [{"role": "user", "content": f"請執行任務：{title}"}],
                                    "agent_id": self.agent_id,
                                    "origin": "kanban_poller"  # 🔒 避免 Bridge 建立重複任務
                                }
                                result_log = "❌ 未知錯誤"
                                async with sess.post(self.bridge_url, json=payload) as chat_resp:
                                    if chat_resp.status == 202:
                                        res_data = await chat_resp.json()
                                        task_result_id = res_data.get('task_id')
                                        poll_url = self.bridge_url.replace("chat/completions", f"task/{task_result_id}")
                                        ans = "⏳ 等待逾時"
                                        for _ in range(150):
                                            await asyncio.sleep(2)
                                            async with sess.get(poll_url) as poll_resp:
                                                if poll_resp.status == 200:
                                                    poll_data = await poll_resp.json()
                                                    if poll_data.get('status') == 'completed':
                                                        ans = poll_data.get('result', '')
                                                        break
                                        result_log = f"✅ 完成\n{ans[:500]}"
                                    elif chat_resp.status == 200:
                                        res_data = await chat_resp.json()
                                        ans = res_data.get('choices', [{}])[0].get('message', {}).get('content', '')
                                        result_log = f"✅ 完成\n{ans[:500]}"
                                    else:
                                        result_log = f"❌ 執行失敗: HTTP {chat_resp.status}"
                                
                                await sess.patch(patch_url, json={"status": "done", "logs": result_log})
                                print(f"✅ [{self.name}] Watcher 任務完成: {title}")
            
            except Exception as e:
                print(f"⚠️ 看板監控異常: {e}")
            
            await asyncio.sleep(60) # 60秒檢查一次

    async def bg_check_gas(self):
        """背景定時檢查 GAS (每30分鐘)"""
        await self.wait_until_ready()
        print(f"⏰ [{self.name}] 背景巡邏已啟動 ({self.check_interval}min/cycle)")
        
        while not self.is_closed():
            try:
                if self.gas_url and self.announce_channel:
                    data = await self.fetch_gas_data()
                    if data and data.get('status') == 'success':
                        new_msgs = []
                        
                        # 檢查新行程
                        current_events = set()
                        for s in data.get('schedule', []):
                            sig = (s['title'], s['time'])
                            current_events.add(sig)
                            if sig not in self.seen_events and self.seen_events: # 非初次啟動才提醒
                                new_msgs.append(f"📅 **新增行程**: {s['time']} {s['title']}")
                        
                        # 檢查新信件
                        current_emails = set()
                        for e in data.get('emails', []):
                            sig = (e['subject'], e['date'])
                            current_emails.add(sig)
                            if sig not in self.seen_emails and self.seen_emails: # 非初次啟動才提醒
                                new_msgs.append(f"📧 **新郵件**: [{e['author']}] {e['subject']}")

                        # 更新記憶
                        self.seen_events = current_events
                        self.seen_emails = current_emails
                        
                        # 發送通知
                        if new_msgs:
                            await self.announce_channel.send(
                                f"🔔 **[{self.name} 提醒]** 老闆，發現新動態：\n" + "\n".join(new_msgs)
                            )
                            print(f"🔔 Sent {len(new_msgs)} notifications.")
                    
            except Exception as e:
                print(f"⚠️ 背景檢查錯誤: {e}")
            
            await asyncio.sleep(self.check_interval * 60)

    async def on_message(self, message):
        if message.author == self.user: return
        if message.author.bot: return  # 🛡️ 忽略所有 Bot 訊息，防止無限迴圈
        self.announce_channel = message.channel
        
        # 🛠️ 初始化引導模式 Check
        if message.content.strip() == "初始化":
            self.setup_mode = True
            self.setup_step = 0
            self.setup_data = {}
            await message.reply(f"🔧 **[{self.name}] 初始化設定精靈啟動**\n請輸入您的名字 (Owner Name)：")
            return

        if getattr(self, "setup_mode", False):
            # 定義問題與預設值
            steps_config = [
                ("owner_name", "請輸入當前用戶名字 (Owner Name)", None),
                ("agent_name", "請輸入我的名字 (Agent Name)", "Agent 2"),
                ("agent_title", "請輸入我的職稱 (Title)", "秘書"),
                ("gender", "請輸入我的性別 (Gender)", "女"),
                ("age", "請輸入我的年齡 (Age)", "20"),
                ("nationality", "請輸入我的國籍 (Nationality)", "台灣"),
                ("owner_call", "最後，我該如何稱呼您 (Owner Call)", "老闆"),
                ("gas_url", "若有 GAS API URL 請輸入", None),
                ("check_interval", "巡邏頻率 (分鐘)", "30")
            ]
            
            current_idx = self.setup_step
            # 處理當前輸入
            if current_idx > 0: # 第0步是剛啟動，無需處理輸入
                prev_field = steps_config[current_idx-1][0]
                prev_default = steps_config[current_idx-1][2]
                content = message.content.strip()
                if not content and prev_default:
                   content = prev_default
                self.setup_data[prev_field] = content

            # 準備下一個問題
            if current_idx < len(steps_config):
                field, q_text, default_val = steps_config[current_idx]
                prompt = f"📝 ({current_idx+1}/{len(steps_config)}) {q_text}"
                if default_val:
                    prompt += f" [預設: {default_val}]"
                await message.reply(prompt)
                self.setup_step += 1
            else:
                # 生成 SOUL.md
                new_soul = (
                    f"# {self.setup_data['agent_name']} - 靈魂特質設定 (SOUL.md)\n\n"
                    f"## 核心檔案\n\n"
                    f"* **姓名**：{self.setup_data['agent_name']}\n"
                    f"* **性別**：{self.setup_data['gender']}\n"
                    f"* **年齡**：{self.setup_data['age']}\n"
                    f"* **國籍**：{self.setup_data['nationality']}\n"
                    f"* **現職**：{self.setup_data['owner_name']} 的{self.setup_data['agent_title']}\n\n"
                    f"## 靈魂背景\n暫無\n\n"
                    f"## 性格與行為準則\n稱呼您為「{self.setup_data['owner_call']}」。\n\n"
                    f"## 系統整合\n"
                    f"* **GAS_URL**：{self.setup_data['gas_url']}\n"
                    f"* **巡邏頻率**：{self.setup_data['check_interval']} (分鐘)\n"
                )
                soul_path = AGENT_DIR / "memory" / "SOUL.md"
                with open(soul_path, "w", encoding="utf-8") as f:
                    f.write(new_soul)
                
                self._load_soul()
                self.setup_mode = False
                await message.reply(f"✅ **設定完成！**\n我是 {self.name}，{self.title}。\n每 {self.check_interval} 分鐘巡邏一次。\n請多多指教，{self.call}！")
            return

        # ⚡ 特殊指令區
        cmd = message.content.strip()

        if cmd == "!進化":
            await message.reply(f"🧬 **[{self.name}]** 收到！正在觸發夜間蒸餾與記憶進化...")
            try:
                base_url = self.bridge_url.replace('/v1/chat/completions', '')
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as sess:
                    async with sess.post(f"{base_url}/v1/harness/night-mode") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            msg = data.get("message", "完成")
                            await message.reply(f"✅ **進化完成！**\n{msg}")
                        else:
                            await message.reply(f"⚠️ Bridge 回應異常 (HTTP {resp.status})")
            except Exception as e:
                await message.reply(f"❌ 進化失敗：{e}")
            return

        if cmd == "!快照":
            await message.reply(f"📸 **[{self.name}]** 正在建立系統快照...")
            try:
                base_url = self.bridge_url.replace('/v1/chat/completions', '')
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as sess:
                    async with sess.post(f"{base_url}/v1/harness/snapshot") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            await message.reply(f"✅ **快照完成！**\n{data.get('message','')}")
                        else:
                            await message.reply(f"⚠️ 快照端點不可用 (HTTP {resp.status})，請在哨兵啟動時自動建立。")
            except Exception as e:
                await message.reply(f"❌ 快照失敗：{e}")
            return

        if cmd == "!狀態":
            bio_path = self.agent_dir / "memory" / "ariel_biography.log"
            if bio_path.exists():
                lines = bio_path.read_text(encoding="utf-8").strip().split("\n")
                last_entry = "\n".join(lines[-10:]) if len(lines) > 10 else "\n".join(lines)
                await message.reply(f"📖 **[{self.name} 最近日記]**\n```\n{last_entry[:800]}\n```")
            else:
                await message.reply(f"📖 **[{self.name}]** 尚無傳記記錄，夜間蒸餾後將自動生成。")
            return

        status = await message.reply(f"📡 {self.name} 正在同步大腦與沙盒記憶...")
        
        # ✅ 重點修樹: create_task 避免阻塞 Discord Heartbeat (Can't keep up 問題)
        asyncio.create_task(self._process_message(message, status))

    async def _process_message(self, message, status):
        """背景處理 Bridge 通訊，確保不阻塞 Discord heartbeat"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=480)) as sess:
                # 🧠 Context Injection (GAS Read/Write)
                context_data = ""
                
                # 1. 寫入偵測 (預約/安排)
                start_match = re.search(r"(預約|安排|Book|新增行程)", message.content, re.IGNORECASE)
                if self.gas_url and start_match:
                    await status.edit(content=f"🧠 {self.name} 正在分析行程內容...")
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    prompt = (
                        f"SYSTEM_Instruction: You are an Event Parser. Current Time: {now_str}.\n"
                        f"Extract event details from user input into JSON format.\n"
                        f"Required fields: title, startTime (YYYY-MM-DD HH:mm), endTime (optional, default 1 hour later).\n"
                        f"User Input: \"{message.content}\"\n"
                        f"Output ONLY the JSON object string (e.g. {{\"title\": \"...\"}}), no markdown, no explanation."
                    )
                    
                    # 呼叫 Bridge 解析 JSON
                    payload = {"messages": [{"role": "user", "content": prompt}], "agent_id": self.agent_id}
                    async with sess.post(self.bridge_url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            raw_json = data.get('choices', [{}])[0].get('message', {}).get('content', '{}')
                        elif resp.status == 202:
                            raw_json = "{}" # 簡化處理
                        else:
                            raw_json = "{}"

                    # 清理 JSON
                    try:
                        json_str = re.search(r"\{.*\}", raw_json, re.DOTALL).group(0)
                        event_data = json.loads(json_str)
                    except:
                        await status.edit(content=f"⚠️ 解析失敗，請確認格式 (例如：明天下午三點開會)")
                        return

                    if event_data.get("title") and event_data.get("startTime"):
                        await status.edit(content=f"📝 正在寫入行程：{event_data['title']}...")
                        res = await self.create_gas_event(event_data)
                        if res and res.get("status") == "success":
                            await status.edit(content=f"✅ **已預約成功！**\n📅 {event_data['startTime']} - {event_data['title']}")
                        else:
                            await status.edit(content=f"❌ 寫入失敗：{res.get('error') if res else 'Unknown'}")
                    else:
                        await status.edit(content=f"⚠️ 資訊不足，請包含標題與時間。")
                    return # 結束

                # 2. 讀取偵測
                if self.gas_url and any(k in message.content for k in ["行程", "Schedule", "信件", "Email", "行事曆"]):
                    await status.edit(content=f"🔍 {self.name} 正在查詢您的行事曆...")
                    gas_data = await self.fetch_gas_data()
                    if gas_data and gas_data.get('status') == 'success':
                        s_list = gas_data.get('schedule', [])
                        schedule_text = "\n".join([f"- {s['time']} {s['title']}" for s in s_list]) if s_list else "(目前無近期行程)"
                        e_list = gas_data.get('emails', [])
                        email_text = "\n".join([f"- [{e['date']}] {e['subject']} (From: {e['from']})" for e in e_list]) if e_list else "(目前無未讀信件)"
                        context_data = (
                            f"\n[系統資訊 - GAS 資料]\n"
                            f"擁有者: {gas_data.get('owner')}\n"
                            f"今日: {gas_data.get('today')}\n"
                            f"近期行程:\n{schedule_text}\n"
                            f"未讀信件:\n{email_text}\n"
                            f"[結束系統資訊]\n"
                        )
                
                # 3. 標準對話流程
                payload = {
                    "messages": [{"role": "user", "content": context_data + message.content}],
                    "agent_id": self.agent_id
                }
                
                async with sess.post(self.bridge_url, json=payload) as resp:
                    data = await resp.json()
                    
                ans = ""
                if resp.status == 202:
                    tid = data.get('task_id')
                    start_time = datetime.datetime.now()
                    while True:
                        await asyncio.sleep(2)
                        elapsed = int((datetime.datetime.now() - start_time).total_seconds())
                        poll_url = self.bridge_url.replace("chat/completions", f"task/{tid}")
                        async with sess.get(poll_url) as poll_resp:
                            if poll_resp.status != 200: continue
                            task_data = await poll_resp.json()
                        if task_data.get('status') == 'completed':
                            ans = task_data.get('result', '')
                            break
                        if elapsed > 0 and elapsed % 30 == 0:
                            try:
                                await status.edit(content=f"⏱️ {self.name} 思考中... (已耗時 {elapsed}s)")
                            except: pass
                        if elapsed > 460:
                            ans = "🚨 代理人端等待逾時 (460s+)"
                            break
                else:
                    ans = data.get('choices', [{}])[0].get('message', {}).get('content', 'Error')
            
            cleaned = self.polish(ans)
            final = f"**[{self.name} {self.title}]**\n" + (cleaned if cleaned.startswith(self.call) else f"{self.call}，內容如下：\n{cleaned}")
            
            # ✂️ Discord 2000 字元限制處理
            if len(final) <= 2000:
                try:
                    await status.edit(content=final)
                except Exception:
                    pass
            else:
                # 智慧分段：盡量切在換行符號或空白處，避免切斷單字或 Markdown 區塊
                chunks = []
                temp_text = final
                while len(temp_text) > 1900:
                    split_idx = temp_text.rfind('\n', 0, 1900)
                    if split_idx == -1:
                        split_idx = temp_text.rfind(' ', 0, 1900)
                    if split_idx == -1:
                        split_idx = 1900
                        
                    chunks.append(temp_text[:split_idx])
                    temp_text = temp_text[split_idx:].lstrip('\n ')
                    
                if temp_text:
                    chunks.append(temp_text)

                try:
                    await status.edit(content=chunks[0] + "\n*(待續...)*")
                    for i in range(1, len(chunks)):
                        await message.channel.send(chunks[i])
                except Exception as e:
                    print(f"🚨 [Discord] 分段傳送失敗: {e}")
            
        except Exception as e:
            try:
                await status.edit(content=f"⚠️ {self.call}，通訊異常：{str(e)}")
            except Exception:
                pass  # 訊息已被刪除，靜默放棄


if __name__ == '__main__':
    ArielAgentNode(intents=discord.Intents.all()).run(os.getenv('DISCORD_TOKEN'), log_level=logging.WARNING)
