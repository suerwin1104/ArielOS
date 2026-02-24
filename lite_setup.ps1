# ArielOS v4.0 - Setup Script (Windows PowerShell 5.1 Compatible)
# Usage: .\lite_setup.ps1

$ErrorActionPreference = "Continue"
$ArielDir = $PSScriptRoot

Write-Host "------------------------------------------------"
Write-Host "   ArielOS v4.0 - Installation Wizard          "
Write-Host "------------------------------------------------"

# 1. Python Check
Write-Host "[1/6] Checking Python..."
$py = python --version 2>&1
if ($LastExitCode -ne 0) {
    Write-Host "EROR: Python not found. Please install Python 3.10+."
    exit 1
}
Write-Host "OK: $py"

# 2. Dependencies
Write-Host "[2/6] Installing dependencies..."
$pkgs = @("flask", "waitress", "requests", "discord.py", "aiohttp", "python-dotenv", "qdrant-client", "sentence-transformers", "PyNaCl", "primp", "pandas", "beautifulsoup4", "schedule")
foreach ($p in $pkgs) {
    Write-Host "Installing $p..."
    pip install $p -q --disable-pip-version-check
}

# 3. Ollama Check
Write-Host "[3/6] Checking Ollama..."
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "OK: Ollama found at $($ollama.Source)"
}
else {
    Write-Host "WARN: Ollama not found. Install from https://ollama.com"
}

# 4. Directories
Write-Host "[4/6] Creating directories..."
$targetPaths = @(
    "backups",
    "Shared_Vault\Memory",
    "Shared_Vault\roles",
    "Central_Bridge\logs",
    "Ariel_Agent_1\memory",
    "Ariel_Agent_2\memory"
)
foreach ($tp in $targetPaths) {
    $fullPath = Join-Path $ArielDir $tp
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        Write-Host "Created: $tp"
    }
    else {
        Write-Host "Exists: $tp"
    }
}

# 5. Env Files
Write-Host "[5/6] Checking .env files..."
$envs = @("Ariel_Agent_1\.env", "Ariel_Agent_2\.env")
foreach ($e in $envs) {
    $epath = Join-Path $ArielDir $e
    if (-not (Test-Path $epath)) {
        "DISCORD_TOKEN=your_token_here" | Set-Content $epath
        Write-Host "Created template: $e"
    }
    else {
        $text = Get-Content $epath -Raw
        if ($text -match "your_token_here") {
            Write-Host "WARN: $e Token not set yet."
        }
        else {
            Write-Host "OK: $e Token is set."
        }
    }
}

# 6. Start Scripts
Write-Host "[6/6] Creating helper scripts..."

# start_bridge.ps1
$bScript = "Set-Location `"$ArielDir\Central_Bridge`"; python ariel_bridge.py"
$bScript | Set-Content (Join-Path $ArielDir "start_bridge.ps1")

# start_agents.ps1
$aScript = "Set-Location `"$ArielDir`"; python ariel_launcher.py --agents"
$aScript | Set-Content (Join-Path $ArielDir "start_agents.ps1")

# start_all.ps1
$allScript = "Set-Location `"$ArielDir`"; Start-Process powershell -ArgumentList '-NoExit -Command `"cd ''$ArielDir\Central_Bridge''; python ariel_bridge.py`"'; Start-Sleep -Seconds 5; python ariel_launcher.py --agents"
$allScript | Set-Content (Join-Path $ArielDir "start_all.ps1")

Write-Host "------------------------------------------------"
Write-Host "Installation Complete!"
Write-Host "Run .\start_all.ps1 to start the system."
Write-Host "------------------------------------------------"
