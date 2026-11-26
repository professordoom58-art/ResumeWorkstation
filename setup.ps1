<#
.SYNOPSIS
  One-time setup for a fresh clone of ResumeWorkstation (safe to re-run; it only adds what is missing).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File setup.ps1
#>
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

Step 'Checking prerequisites'
$missing = @()
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) { $missing += 'Python 3.11 (python.org)' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $missing += 'Node.js 18+ (nodejs.org)' }
if (-not (Test-Path 'C:\Program Files\Google\Chrome\Application\chrome.exe')) { $missing += 'Google Chrome' }
try { $w = New-Object -ComObject Word.Application; $w.Quit() } catch { $missing += 'Microsoft Word (needed for PDF export)' }
if ($missing) { Write-Host "Missing: $($missing -join ', ')" -ForegroundColor Yellow; exit 1 }

if (-not (Test-Path .venv\Scripts\python.exe)) {
  Step 'Creating Python virtual environment (.venv)'
  if (Get-Command py -ErrorAction SilentlyContinue) { py -3.11 -m venv .venv } else { python -m venv .venv }
}
Step 'Installing Python packages'
& .venv\Scripts\python.exe -m pip install -q --upgrade pip
& .venv\Scripts\python.exe -m pip install -q -r requirements.txt

Step 'Installing browser helper (playwright-core)'
Push-Location src\browser; npm install --silent; Pop-Location

Step 'Creating private folders'
foreach ($d in 'profile', 'jobs', 'outbox', 'tailored', 'resumes') { New-Item -ItemType Directory -Force $d | Out-Null }
if (-not (Test-Path outbox\sent_all.json)) { '{}' | Out-File -Encoding ascii outbox\sent_all.json; Write-Host '    created empty duplicate guard outbox\sent_all.json' }

Step 'Verifying'
& .venv\Scripts\python.exe -c "import jobspy, openpyxl, docx, pymupdf, requests; print('    python packages ok')"
node -e "require('./src/browser/node_modules/playwright-core'); console.log('    playwright-core ok')"

Write-Host ''
Write-Host 'Setup complete. Next:' -ForegroundColor Green
Write-Host '  1. node src\browser\start.js   (sign in to Gmail and WhatsApp Web once in that Chrome window)'
Write-Host '  2. Open your AI agent here and send:  start + your resume + (optional) your Telegram bot token'
