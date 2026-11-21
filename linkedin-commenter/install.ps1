# One-command setup for the LinkedIn GTM commenting routine (Windows PowerShell).
#
#   irm https://raw.githubusercontent.com/rohitabrahamgeorge/rohitabrahamgeorge/claude/linkedin-engagement-automation-h7dz64/linkedin-commenter/install.ps1 | iex
#
# Clones the repo, installs Playwright, checks Claude Code, opens a LinkedIn login window,
# and registers a Task Scheduler job for Mon/Wed/Fri 10:30 local time (wakes the PC if asleep).
$ErrorActionPreference = "Stop"
$Branch = "claude/linkedin-engagement-automation-h7dz64"
$Dir = Join-Path $HOME "linkedin-commenter-repo"
function Say($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

Say "1/5 Getting the routine files into $Dir"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { winget install --id Git.Git -e --silent; $env:Path += ";C:\Program Files\Git\cmd" }
if (Test-Path "$Dir\.git") { git -C $Dir pull -q --ff-only origin $Branch } else { git clone -q -b $Branch https://github.com/rohitabrahamgeorge/rohitabrahamgeorge.git $Dir }
Set-Location $Dir

Say "2/5 Installing Playwright"
$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Py) { winget install --id Python.Python.3.12 -e --silent; $Py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" }
& $Py -m pip install -q --upgrade playwright
& $Py -m playwright install chromium

Say "3/5 Checking Claude Code"
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { irm https://claude.ai/install.ps1 | iex; $env:Path += ";$HOME\.local\bin" }
$Claude = (Get-Command claude).Source
& $Claude -p "Reply with the word ok" *> $null
if ($LASTEXITCODE -ne 0) { Write-Host "Sign in to Claude Code, then type /exit."; & $Claude }

Say "4/5 LinkedIn login (a browser window opens; log in and finish any 2FA)"
if (-not ((& $Py linkedin-commenter\scripts\li.py check) -match '"logged_in": true')) {
  & $Py linkedin-commenter\scripts\li.py login
  if (-not ((& $Py linkedin-commenter\scripts\li.py check) -match '"logged_in": true')) { throw "LinkedIn login not detected. Re-run the installer." }
}

Say "5/5 Scheduling Mon/Wed/Fri 10:30"
$Runner = Join-Path $Dir "linkedin-commenter\run.ps1"
@"
Set-Location "$Dir"
git pull -q --ff-only origin $Branch 2>`$null
New-Item -ItemType Directory -Force linkedin-commenter\state | Out-Null
"=== `$(Get-Date) ===" | Add-Content linkedin-commenter\state\run.log
& "$Claude" -p "/linkedin-gtm-commenter Run today's routine: 25 comments, then show me the report." --permission-mode dontAsk --allowedTools Skill Read Write Edit Glob Grep "Bash(python:*)" "Bash(python3:*)" "Bash(git:*)" "Bash(sleep:*)" "Bash(Start-Sleep:*)" "PowerShell" *>> linkedin-commenter\state\run.log
"@ | Set-Content $Runner

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Wednesday,Friday -At 10:30am
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName "LinkedIn GTM comments" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "`nAll set. Runs on its own every Mon/Wed/Fri at 10:30 (wakes the PC; catches up if it was off)."
Write-Host "Reports: $Dir\linkedin-commenter\reports\   Log: $Dir\linkedin-commenter\state\run.log"
Write-Host "Test now: powershell -File `"$Runner`"    Remove: Unregister-ScheduledTask 'LinkedIn GTM comments'"
