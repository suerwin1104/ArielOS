\# Ariel OS Lite - 分散式大小腦助理系統



Ariel OS Lite 是一個基於「大小腦架構」的輕量化個人 AI 助理，專為多裝置（如 S9、OPPO N3、Docker）設計。



\## 🌟 核心特色：大小腦技術 (Edge-Cloud Hybrid)

\* \*\*⚡ 本地小腦 (Local Cerebellum):\*\* 部署於各終端設備。使用 `0.5B` 等極輕量模型，確保日常瑣事、感官同步（GAS）秒讀秒回。

\* \*\*🧠 私有大腦 (Private Cerebrum):\*\* 透過 \*\*Tailscale 加密隧道\*\* 橋接至高效能主機。當遇到複雜任務時，系統自動將算力槓桿至遠端大腦。

\* \*\*🔗 算力共享橋接器:\*\* 獨有的本地橋接設計，讓您的手機也能擁有桌機等級的推理能力，且無需支付高額 API 費用。

🖥️ 遠端大腦端 (Windows / OpenClaw) 安裝
若要將 Win OS 的 OpenClaw 作為大腦，請在 Win OS 下載本倉庫後，執行：

PowerShell
./install_bridge.ps1
此腳本會自動將橋接器整合進您的 .openclaw 環境中。

🧠 Ariel OS：雲端大腦連線指南 (OpenClaw 聯動)
本系統透過 Win11 本地橋接器 (Ariel Bridge) 實現 Docker 環境與主機端 OpenClaw 算力的完美對接。

1. 技術架構
用戶端 (Ariel-Docker): 發送指令至 Tailscale IP:28888。

橋接器 (Ariel-Bridge): 運行於 Win11，負責過濾關鍵字並調度任務。

核心大腦 (OpenClaw CLI): 執行 main 代理人，調用 gemini-3-flash 進行深度推理。

2. 如何觸發大腦模式
指令中只要包含 「大腦」 關鍵字，系統會自動切換至雲端模式，將需求拋接給 OpenClaw。

範例指令：大腦，分析今日台灣前 3 條重大新聞

回傳限制：自動處理 Discord 2000 字元上限，超過部分將進行安全截斷。

3. 本地導航模式 (Legacy Success Mode)
若指令涉及檔案操作，橋接器將直接在主機硬碟執行任務，不消耗雲端 Token。

列出目錄：指令包含「有哪些、目錄、清單」。

讀取內容：指令包含「讀取、內容」。

📱 Android 平板 / 手機安裝指南 (救火隊模式)
當您的主力伺服器或 Docker 環境不可用時，您可以將 Android 設備 (推薦使用三星 S9 平板等高效能設備) 變身為緊急指揮中心。

1. 準備環境
由於 Android 不直接支援標準 Docker，我們使用 Termux 作為運行環境：

從 F-Droid 下載並安裝 Termux。

安裝 Tailscale Android App 並登入，確保設備能連通 Win11 橋接器。

2. 一鍵快速部署
在 Termux 中複製並貼上以下指令，自動完成環境搭建：

Bash
# 更新系統與安裝必要套件
pkg update -y && pkg upgrade -y
pkg install python git -y

# 克隆專案 (請替換為您的倉庫網址)
git clone https://github.com/您的帳號/ArielOS.git
cd ArielOS

# 安裝 Python 依賴
pip install discord.py requests python-dotenv
3. 配置與啟動
修改環境變數：
使用 nano .env 指令，將您的 Discord Bot Token 與 Win11 Tailscale IP 填入。

執行 Ariel：

Bash
python ariel_main.py
💡 注意事項：

平板端執行的是「通訊與邏輯層」，複雜的大腦推理（Gemini 3 Flash）仍會透過網路由 Win11 端處理。

建議在三星平板上開啟「阻斷所有干擾」模式，並確保 Termux 的「電池最佳化」已關閉，以維持連線穩定。

\## 🔐 認證與擴充

參考 OpenClaw 邏輯，本系統支援：

1\.  \*\*Local/Bridge 模式:\*\* 完全私有化，不經由第三方雲端。

2\.  \*\*API/OAuth 模式:\*\* 預留 Model Resolver 接口，支援 Google Antigravity OAuth 認證。




