import requests
import sys

def get_weather(location="Taipei"):
    try:
        # 增加 Timeout 至 20 秒，因為 wttr.in 有時較慢
        # 使用 format=3 獲取單行天氣預報
        url = f"https://wttr.in/{location}?format=3"
        response = requests.get(url, timeout=20)
        
        if response.status_code == 200:
            weather_data = response.text.strip()
            print(f"[免費氣象技能] 查詢地點: {location}")
            print(f"目前天氣狀況: {weather_data}")
        else:
            print(f"[免費氣象技能錯誤] 無法取得 {location} 的天氣資訊 (HTTP {response.status_code})。服務可能暫時不可用，請稍後重試。")
    except requests.exceptions.Timeout:
        print(f"[免費氣象技能錯誤] 連線 wttr.in 氣象伺服器逾時。伺服器可能正在維護中，請稍後重試。")
    except Exception as e:
        print(f"[免費氣象技能異常] 連線失敗: {str(e)}")

if __name__ == "__main__":
    # 允許直接傳入引數測試 (過濾常見問法)
    if len(sys.argv) > 1:
        query = sys.argv[1]
        
        # 簡單地名萃取
        target = "Taipei" # 預設
        if "台北" in query: target = "Taipei"
        elif "新北" in query: target = "New Taipei"
        elif "台中" in query: target = "Taichung"
        elif "高雄" in query: target = "Kaohsiung"
        elif "台南" in query: target = "Tainan"
        elif "桃園" in query: target = "Taoyuan"
        elif "新竹" in query: target = "Hsinchu"
        elif "宜蘭" in query: target = "Yilan"
        elif "花蓮" in query: target = "Hualien"
        elif "台東" in query: target = "Taitung"
        elif "嘉義" in query: target = "Chiayi"
        elif "苗栗" in query: target = "Miaoli"
        elif "彰化" in query: target = "Changhua"
        elif "南投" in query: target = "Nantou"
        elif "雲林" in query: target = "Yunlin"
        elif "屏東" in query: target = "Pingtung"
        else: target = query # 若無匹配，直接使用原字串 (可能包含英文城市)
            
        get_weather(target)
    else:
        get_weather()
