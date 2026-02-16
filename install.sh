@"
#!/bin/bash
echo "Ariel OS Lite Installation Start..."
pkg update && pkg upgrade -y
pkg install python git ollama -y
ollama serve & 
sleep 5
echo "Ollama Pulling Model..."
ollama pull qwen2.5:1.5b
git clone https://github.com/suerwin1104/arielos.git
cd arielos
pip install discord.py aiohttp python-dotenv
echo "Done! Please edit .env and run python ariel_launcher.py"
"@ | Out-File -FilePath install.sh -Encoding ascii