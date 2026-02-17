# ArielOS Bridge 自動安裝腳本 (Windows 專用)
$openclawPath = "$home\.openclaw"
$bridgeFile = "ariel_bridge.py"

# 1. 檢查 .openclaw 資料夾是否存在
if (-Not (Test-Path -Path $openclawPath)) {
    Write-Host "⚠️ 找不到 .openclaw 資料夾，正在為您建立..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $openclawPath
}

# 2. 從當前目錄複製橋接器檔案
if (Test-Path -Path ".\$bridgeFile") {
    Copy-Item -Path ".\$bridgeFile" -Destination $openclawPath -Force
    Write-Host "✅ 已成功將 $bridgeFile 安裝至 $openclawPath" -ForegroundColor Green
} else {
    Write-Host "❌ 找不到來源檔案 $bridgeFile，請確保您是在倉庫根目錄執行此腳本。" -ForegroundColor Red
}

# 3. 提示使用者啟動方式
Write-Host "`n🚀 安裝完成！您可以執行以下指令啟動橋接器：" -ForegroundColor Cyan
Write-Host "cd $openclawPath"
Write-Host "python $bridgeFile"
