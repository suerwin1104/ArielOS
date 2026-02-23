import requests
import sys
import datetime

def get_recent_earthquakes():
    try:
        # 使用 USGS (美國地質調查局) 的免費公開 API (不需要 API Key)
        # 這裡獲取過去 24 小時內，規模 4.5 以上的全球顯著地震
        url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            features = data.get("features", [])
            
            if not features:
                print("[免費地震技能] 報告：過去 24 小時內無規模 4.5 以上的顯著地震紀錄。")
                return
                
            print(f"[免費地震技能] 過去 24 小時內規模 4.5 以上之前 {min(5, len(features))} 筆地震報表：\n")
            
            for i, eq in enumerate(features[:5]):
                props = eq["properties"]
                place = props.get("place", "未知地點")
                mag = props.get("mag", "未知")
                time_ms = props.get("time", 0)
                
                # 將毫秒時間戳轉換為我們可讀的當地時間
                eq_time = datetime.datetime.fromtimestamp(time_ms / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
                
                print(f"{i+1}. {eq_time} | 規模: {mag} | 地點: {place}")
        else:
            print(f"[免費地震技能錯誤] 無法取得地震資訊 (HTTP {response.status_code})")
    except Exception as e:
        print(f"[免費地震技能異常] 連線失敗: {str(e)}")

if __name__ == "__main__":
    get_recent_earthquakes()
