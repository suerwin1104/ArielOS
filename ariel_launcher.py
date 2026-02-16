import subprocess, time, sys

def run_sentinel():
    print("🛰️ [Lite Sentinel] 哨兵啟動。守護 Ariel 離線版...")
    while True:
        process = subprocess.Popen([sys.executable, "ariel_main.py"])
        process.wait()
        if process.returncode != 0:
            print(f"⚠️ 偵測到異常退出，5秒後自癒重啟...")
            time.sleep(5)
        else:
            time.sleep(2)

if __name__ == "__main__":
    run_sentinel()