from flask import Flask, request, jsonify
import os, subprocess

app = Flask(__name__)

# --- [設定根目錄：Ariel 的本地活動範圍] ---
ROOT_DIR = r"C:\Users\USER\.openclaw\workspace"

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    try:
        data = request.json
        prompt = data['messages'][-1]['content']
        print(f"📡 收到指令: {prompt}")

        # --- 🌟 邏輯 A：大腦需求拋接 (關鍵字觸發) ---
        if "大腦" in prompt:
            requirement = prompt.replace("大腦", "").strip()
            print(f"🧠 需求已拋給 OpenClaw (Agent: main): {requirement}")
            
            # 使用校準後的正確語法
            command = f'openclaw agent --agent main -m "{requirement}" --no-color'
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', shell=True)
            
            answer = process.stdout.strip() or process.stderr.strip()
            
            # 解決 Discord 2000 字限制 (報錯 50035 修正)
            if len(answer) > 1900:
                answer = answer[:1900] + "\n\n(✨ 內容過長已自動截斷)"
                
            return jsonify({"choices": [{"message": {"content": answer}}]})

        # --- 邏輯 B：列出目錄 (完全復原您的成功代碼) ---
        elif any(k in prompt for k in ["目錄", "清單", "資料夾", "有哪些"]):
            files = os.listdir(ROOT_DIR)
            file_list = "\n".join([f"📁 {f}" if os.path.isdir(os.path.join(ROOT_DIR, f)) else f"📄 {f}" for f in files])
            reply = f"🏠 【本地目錄清單】\n路徑：{ROOT_DIR}\n\n{file_list}"

        # --- 邏輯 C：讀取文件 (完全復原您的成功代碼) ---
        elif "讀取" in prompt or "內容" in prompt:
            target_file = None
            for f in os.listdir(ROOT_DIR):
                if f in prompt: target_file = f
            
            if not target_file:
                return jsonify({"choices": [{"message": {"content": "💡 老闆，請告訴我要讀取目錄中的哪個檔案？"}}]})

            file_path = os.path.join(ROOT_DIR, target_file)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            reply = f"🏠 【檔案內容：{target_file}】\n\n{content[:1800]}"

        # --- 預設回覆 ---
        else:
            reply = "✅ Ariel 導航員在線。請說「大腦 + 需求」來調用 Gemini 3。"

        return jsonify({"choices": [{"message": {"content": reply}}]})
        
    except Exception as e:
        return jsonify({"choices": [{"message": {"content": f"❌ 執行出錯：{str(e)}"}}]})

if __name__ == '__main__':
    # 🌟 0.0.0.0 確保跨裝置通訊
    app.run(host='0.0.0.0', port=28888)
