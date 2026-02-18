from flask import Flask, request, jsonify
import subprocess

app = Flask(__name__)

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    try:
        data = request.json
        soul = data.get('soul', '')
        time_ctx = data.get('time_context', '') # 接收來自各特工的時間
        prompt = data['messages'][-1]['content']
        
        print(f"📡 [總部] 收到請求 | 時間: {time_ctx} | 指令: {prompt[:15]}...")

        # 🚀 成功核心邏輯：組合靈魂、時間與用戶指令
        # 處理引號衝突，並確保 openclaw 能在 Windows 環境下被正確呼叫
        safe_text = f"{soul}\n\n{time_ctx}\n\n指令：{prompt}".replace('"', "'")
        command = f'openclaw agent --agent main -m "{safe_text}" --no-color'
        
        # 恢復 shell=True 確保指令路徑正確
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', shell=True)
        
        answer = process.stdout.strip() or process.stderr.strip()
        if not answer: answer = "（大腦連線正常，但目前暫無回應）"

        return jsonify({"choices": [{"message": {"content": answer}}]})
        
    except Exception as e:
        return jsonify({"choices": [{"message": {"content": f"🚨 總部轉接故障：{str(e)}"}}]})

if __name__ == '__main__':
    print("🏰 Ariel OS 蜂巢總部已啟動 | 監聽端口 28888")
    app.run(host='0.0.0.0', port=28888)
