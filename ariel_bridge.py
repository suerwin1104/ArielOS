from flask import Flask, request, jsonify
import os, subprocess

app = Flask(__name__)
ROOT_DIR = r"C:\Users\USER\.openclaw\workspace"

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    try:
        data = request.json
        prompt = data['messages'][-1]['content']
        
        # --- 🧠 邏輯 A：大腦模式 (具備連線診斷) ---
        if "小腦" not in prompt:
            print(f"🧠 嘗試啟動大腦...")
            try:
                # 增加 60 秒超時保護，防止無限期等待
                command = f'openclaw agent --agent main -m "{prompt}" --no-color'
                process = subprocess.run(
                    command, 
                    capture_output=True, text=True, encoding='utf-8', 
                    shell=True, timeout=60
                )

                if process.returncode == 0:
                    reply = process.stdout.strip()
                else:
                    # 🚀 故障診斷：當 OpenClaw 噴出錯誤時
                    err_msg = process.stderr.strip()
                    reply = f"🚨 【大腦暫時斷線】\n原因：{err_msg}\n\n💡 排除建議：\n1. 請檢查 Win11 是否進入休眠。\n2. 確認 OpenClaw Gateway 是否已啟動。\n3. 您可以改用「小腦 + 指令」來處理本地任務。"
            
            except subprocess.TimeoutExpired:
                reply = "⏳ 【大腦反應超時】\nGemini 3 Flash 思考太久或網路不穩，請稍後再試。"
            except Exception as e:
                reply = f"❌ 【大腦系統崩潰】\n錯誤訊息：{str(e)}"

        # --- 📂 邏輯 B：小腦模式 (始終保持在線) ---
        else:
            # (此處保留您原有的成功版小腦邏輯...)
            reply = "🏠 【小腦模式】檔案系統運作正常，大腦斷線不影響我跑腿！"

        return jsonify({"choices": [{"message": {"content": reply}}]})
        
    except Exception as e:
        return jsonify({"choices": [{"message": {"content": f"❌ 總系統異常：{str(e)}"}}]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=28888)
