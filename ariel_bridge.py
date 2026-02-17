from flask import Flask, request, jsonify
import os, subprocess

app = Flask(__name__)
ROOT_DIR = r"C:\Users\USER\.openclaw\workspace"

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    try:
        data = request.json
        prompt = data['messages'][-1]['content']
        # 只要日誌有出現這一行，就代表 Docker 有成功連過來
        print(f"📡 [連線成功] 收到指令: {prompt}")

        # --- 📂 邏輯 B：【小腦模式】當指令包含「小腦」時，執行本地檔案任務 ---
        if "小腦" in prompt:
            print(f"📁 啟動本地小腦邏輯...")
            clean_prompt = prompt.replace("小腦", "").strip()

            # 復原您最滿意的 LS (目錄) 邏輯
            if any(k in clean_prompt for k in ["目錄", "清單", "資料夾", "有哪些"]):
                files = os.listdir(ROOT_DIR)
                file_list = "\n".join([f"📁 {f}" if os.path.isdir(os.path.join(ROOT_DIR, f)) else f"📄 {f}" for f in files])
                reply = f"🏠 【小腦回報：本地目錄】\n{file_list}"
            
            # 復原您最滿意的 CAT (讀取) 邏輯
            elif "讀取" in clean_prompt or "內容" in clean_prompt:
                target_file = None
                for f in os.listdir(ROOT_DIR):
                    if f in clean_prompt: target_file = f
                
                if not target_file:
                    reply = "💡 小腦找不到檔案，請指名檔名。"
                else:
                    file_path = os.path.join(ROOT_DIR, target_file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reply = f"🏠 【小腦讀取：{target_file}】\n\n{f.read()[:1800]}"
            else:
                reply = "💡 小腦在線，目前僅支援目錄清單與檔案讀取。"
            
            return jsonify({"choices": [{"message": {"content": f"{reply}\n\n來源: [Win11 小腦]"}}]})

        # --- 🧠 邏輯 A：【預設模式】不包含小腦時，強制全部走大腦 ---
        else:
            print(f"🧠 召喚大腦 Gemini 3 Flash...")
            # 修正：移除所有干擾，直接拋給 main 代理人
            command = f'openclaw agent --agent main -m "{prompt}" --no-color'
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', shell=True, timeout=90)
            
            answer = process.stdout.strip() or process.stderr.strip()
            
            if len(answer) > 1900:
                answer = answer[:1900] + "\n\n(內容過長已裁切)"
                
            return jsonify({"choices": [{"message": {"content": f"{answer}\n\n來源: [Win11 大腦]"}}]})
        
    except Exception as e:
        print(f"❌ 錯誤: {str(e)}")
        return jsonify({"choices": [{"message": {"content": f"❌ 橋接器執行異常：{str(e)}"}}]})

if __name__ == '__main__':
    print("="*50)
    print("🚀 Ariel Bridge [預設大腦模式 - 啟動中]")
    print(f"📂 本地工作區：{ROOT_DIR}")
    print("="*50)
    app.run(host='0.0.0.0', port=28888)
