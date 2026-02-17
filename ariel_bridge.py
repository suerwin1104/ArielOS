from flask import Flask, request, jsonify
import os, subprocess

app = Flask(__name__)

# 📝 設定：請確保此路徑與您的 OpenClaw 工作區一致
ROOT_DIR = r"C:\Users\USER\.openclaw\workspace"

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    try:
        data = request.json
        # 接收來自 Docker 端的「動態靈魂」與「環境背景」
        soul = data.get('soul', '妳是一位專業的 AI 助手。')
        time_ctx = data.get('time_context', '')
        prompt = data['messages'][-1]['content']
        
        print(f"📡 接收請求 | 長度: {len(prompt)} | 包含人格: {'是' if soul else '否'}")

        # --- 📂 邏輯 A：【小腦工具層】僅在明確指名時觸發 ---
        if "小腦" in prompt:
            clean_prompt = prompt.replace("小腦", "").strip()
            
            # 1. 目錄清單 (ls)
            if any(k in clean_prompt for k in ["目錄", "清單", "資料夾", "有哪些"]):
                files = os.listdir(ROOT_DIR)
                reply = "\n".join([f"📁 {f}" if os.path.isdir(os.path.join(ROOT_DIR, f)) else f"📄 {f}" for f in files])
                return jsonify({"choices": [{"message": {"content": f"🏠 本地目錄回報：\n{reply}"}}]})
            
            # 2. 檔案讀取 (cat)
            elif any(k in clean_prompt for k in ["讀取", "內容"]):
                target = next((f for f in os.listdir(ROOT_DIR) if f in clean_prompt), None)
                if target:
                    with open(os.path.join(ROOT_DIR, target), 'r', encoding='utf-8') as f:
                        return jsonify({"choices": [{"message": {"content": f.read()[:1800]}}]})
            
            # 💡 隱藏邏輯：如果只說「小腦」但沒指令，不回廢話，直接讓它滑入大腦對話模式

        # --- 🧠 邏輯 B：【大腦對話層】注入人格，由 Gemini 3 全權負責 ---
        # 構造 OpenClaw 最終指令：人格 + 時間 + 用戶問題
        full_input = f"{soul}\n\n{time_ctx}\n\n用戶指令：{prompt}"
        
        # 執行 OpenClaw (確保使用 main 代理人)
        command = f'openclaw agent --agent main -m "{full_input}" --no-color'
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', shell=True)
        
        answer = process.stdout.strip() or process.stderr.strip()
        
        # 裁切過長內容，確保 Discord 傳輸成功
        if len(answer) > 1900:
            answer = answer[:1900] + "\n\n(✨ 內容過長已自動截斷)"

        return jsonify({"choices": [{"message": {"content": answer}}]})
        
    except Exception as e:
        print(f"❌ 錯誤: {str(e)}")
        return jsonify({"choices": [{"message": {"content": f"🚨 橋接器暫時異常：{str(e)}"}}]})

if __name__ == '__main__':
    print("="*50)
    print("🚀 Ariel Bridge [GitHub 專業版] 啟動成功")
    print("✨ 特點：動態人格注入、無感工具切換、Gemini 3 核心驅動")
    print("="*50)
    app.run(host='0.0.0.0', port=28888)
