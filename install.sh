@"
#!/bin/bash
echo "🛰️ Ariel OS Lite 一鍵安裝啟動..."
pkg update && pkg upgrade -y
pkg install python git ollama -y
ollama serve & 
sleep 5
echo "🧠 正在下載大腦模型 (1.5b)..."
ollama pull qwen2.5:1.5b
git clone https://github.com/suerwin1104/arielos.git
cd arielos
pip install discord.py aiohttp python-dotenv
echo "-----------------------------------------------"
echo "✅ Ariel OS Lite 安裝完成！"
echo "👉 請輸入 'nano .env' 填入您的 DISCORD_TOKEN"
echo "👉 最後輸入 'python ariel_launcher.py' 啟動"
echo "-----------------------------------------------"
"@ | Out-File -FilePath install.sh -Encoding ascii