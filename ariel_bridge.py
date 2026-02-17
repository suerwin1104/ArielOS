from flask import Flask, request, jsonify
import os, subprocess

app = Flask(__name__)
# 預設 OpenClaw 工作區路徑
ROOT_DIR = r"C:\Users\USER\.openclaw\workspace"

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    try:
        data = request.json
        soul = data.get('soul', '')
        time_ctx = data.get('time_context', '')
        prompt = data['messages'][-1]['content']
        print(f"📡 接收請求: {prompt[:20]}...")

        # --- 📂 隱形工具層 (小腦) ---
        # 僅在提到「小腦」且包含明確動作時攔截，不回廢話
        if "小腦" in prompt:
            clean_prompt = prompt.replace("小腦", "").strip()
            
            # 檔案清單邏輯
            if any(k in clean_prompt for k in ["目錄", "清單", "資料夾", "有哪些"]):
                files = os.listdir(ROOT_DIR)
                reply = "\n".join([f"📁 {f}" if os.path.isdir(os.path.join(ROOT_DIR, f)) else f"📄 {f}" for f in files])
                return jsonify({"choices": [{"message": {"content": f"🏠 本地目錄回報：\n{reply}"}}]})
            
            # 檔案讀取邏輯
            elif any(k in clean_prompt for k in ["讀取", "內容"]):
                target = next((f for f in os.listdir(ROOT_DIR) if f in clean_prompt), None)
                if target:
                    file_path = os.path.join(ROOT_DIR, target)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return jsonify({"choices": [{"message": {"content": f.read()[:1800]}}]})

        # --- 🧠 夥伴對話層 (大腦) ---
        # 整合靈魂、時間與指令，拋給 OpenClaw 的 Gemini 3 Flash
        full_input = f"{soul}\n\n{time_ctx}\n\n用戶最新指令：{prompt}"
        
        command = f'openclaw agent --agent main -m "{full_input}" --no-color'
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', shell=True)
        
        answer = process.stdout.strip() or process.stderr.strip()
        
        # 裁切內容確保符合 Discord 上限
        if len(answer) > 1900:
            answer = answer[:1900] + "\n\n(✨ 內容過長已自動截斷)"

        return jsonify({"choices": [{"message": {"content": answer}}]})
        
    except Exception as e:
        print(f"❌ 錯誤: {str(e)}")
        return jsonify({"choices": [{"message": {"content": f"🚨 系統微調中：{str(e)}"}}]})

if __name__ == '__main__':
    print("🚀 Ariel Bridge [通用夥伴版] 啟動成功")
    app.run(host='0.0.0.0', port=28888)
