from playwright.sync_api import sync_playwright

def debug_google_ai():
    query = "如何製作手工肥皂的原理"
    print(f"啟動 Debug 抓取: {query}")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            search_url = f"https://www.google.com/search?q={query}"
            page.goto(search_url, timeout=30000)
            
            # 等待 5 秒讓頁面加載
            page.wait_for_timeout(5000)
            
            # 建立截圖與 HTML 備份
            page.screenshot(path="debug_google_ai.png")
            with open("debug_google_ai.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            
            print("截圖與 HTML 已保存。檢查是否有 AI 摘要或被阻擋。")
            
            # 檢查選擇器
            has_ai = page.locator('[aria-label*="AI 摘要"]').count() > 0
            has_sge = page.locator('div[data-as-type="sge"]').count() > 0
            has_captcha = page.locator('form[action="/sorry/index"]').count() > 0
            has_cookie = page.locator('text="我同意"').count() > 0 or page.locator('text="I agree"').count() > 0
            
            print(f"AI 摘要 aria-label 存在: {has_ai}")
            print(f"AI 摘要 SGE data-as-type 存在: {has_sge}")
            print(f"偵測到 CAPTCHA: {has_captcha}")
            print(f"偵測到 Cookie 橫幅: {has_cookie}")
            
            browser.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_google_ai()
