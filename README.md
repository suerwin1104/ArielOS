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


\## 🔐 認證與擴充

參考 OpenClaw 邏輯，本系統支援：

1\.  \*\*Local/Bridge 模式:\*\* 完全私有化，不經由第三方雲端。

2\.  \*\*API/OAuth 模式:\*\* 預留 Model Resolver 接口，支援 Google Antigravity OAuth 認證。


