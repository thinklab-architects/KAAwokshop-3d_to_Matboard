# One-time setup: create .venv, install Python deps, check the SketchUp DLL.
#
# The front-end is shipped pre-built in web/dist, so Node is optional - it is
# only needed to change anything under web/src. This script builds it when Node
# happens to be there, and says nothing when it is not.

[CmdletBinding()]
param(
    # Skip the npm install/build even if Node is available.
    [switch]$NoWeb
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "   $msg" -ForegroundColor Yellow }

# A .venv copied in with the rest of the folder still has a python.exe, but its
# pyvenv.cfg names an interpreter path from the machine it was built on. Only
# actually running it tells the two cases apart.
function Test-Venv {
    param([string]$exe)
    if (-not (Test-Path $exe)) { return $false }
    try {
        $null = & $exe -c 'import sys' 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

# Provisioned means it also has the dependencies, not just an interpreter.
function Test-Provisioned {
    param([string]$exe)
    if (-not (Test-Path $exe)) { return $false }
    try {
        $null = & $exe -c 'import uvicorn, numpy, reportlab' 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

# --- Bundled runtime ------------------------------------------------------
# When the folder ships with runtime\ there is nothing to install: skip straight
# to the DLL check. This is the path a recipient takes, and it needs no Python
# on the machine, no admin rights and no network.
$bundled = Join-Path $root 'runtime\python.exe'
$skipPython = $false
if (Test-Provisioned $bundled) {
    Step '執行環境'
    Ok '已內附 Python 執行環境（runtime\），不需要安裝任何東西'
    $venvPy = $bundled
    $skipPython = $true
}

if (-not $skipPython) {

# --- Python ---------------------------------------------------------------
Step 'Python'
# The py launcher is the reliable one on Windows; bare `python` may be the Store
# stub that only opens the Store page.
$pyCmd = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyCmd = 'py'; $pyArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyCmd = 'python'
} else {
    Write-Host '找不到 Python。請先安裝 Python 3.11 以上：https://www.python.org/downloads/' -ForegroundColor Red
    Write-Host '安裝時記得勾選 "Add python.exe to PATH"。' -ForegroundColor Red
    exit 1
}
# Read the version from `--version` rather than a -c one-liner: Windows
# PowerShell 5.1 strips the double quotes out of an argument on its way to a
# native command, so `print("%d.%d" % ...)` reaches Python as a syntax error.
# setup.cmd runs 5.1, so anything passed to python here must avoid quotes.
$verRaw = (& $pyCmd @pyArgs --version 2>&1) -join ' '
if ($LASTEXITCODE -ne 0 -or $verRaw -notmatch '(\d+)\.(\d+)') {
    Write-Host "Python 無法執行（$pyCmd）。請重新安裝 Python 3.11 以上。" -ForegroundColor Red
    exit 1
}
$ver = "$($Matches[1]).$($Matches[2])"
Ok "使用 Python $ver"
if ([version]$ver -lt [version]'3.11') {
    Write-Host "需要 Python 3.11 以上，目前是 $ver。" -ForegroundColor Red
    exit 1
}

$venvDir = Join-Path $root '.venv'
$venvPy = Join-Path $venvDir 'Scripts\python.exe'
if (Test-Venv $venvPy) {
    Ok '.venv 已存在，沿用'
} else {
    if (Test-Path $venvDir) {
        Step '.venv 無法執行，重建中'
        Warn '（這個 .venv 多半是連同資料夾從別台機器複製過來的）'
    } else {
        Step '建立虛擬環境 .venv'
    }
    & $pyCmd @pyArgs -m venv $venvDir
    if (-not (Test-Venv $venvPy)) { Write-Host '建立 .venv 失敗。' -ForegroundColor Red; exit 1 }
    Ok '完成'
}

Step '安裝 Python 套件'
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r (Join-Path $root 'requirements.txt') --quiet
if ($LASTEXITCODE -ne 0) { Write-Host '套件安裝失敗。' -ForegroundColor Red; exit 1 }
Ok 'numpy · fastapi · uvicorn · reportlab 就緒'

}  # end of the "no bundled runtime" branch

# --- SketchUpAPI.dll ------------------------------------------------------
# Asked of sdk.py itself instead of re-implementing the search, so setup and the
# server can never disagree about which DLL is in play. Importing it actually
# loads the library, which also catches a DLL whose own dependencies are missing
# - a file-exists check would call that a pass and the server would still die.
Step '檢查 SketchUpAPI.dll'
$converter = Join-Path $root 'converter'
$found = & $venvPy -c @"
import sys
sys.path.insert(0, r'$converter')
try:
    from skp2web import sdk
except Exception:
    sys.exit(1)
print(sdk.DLL_PATH)
"@
if ($LASTEXITCODE -eq 0 -and $found) {
    Ok "找到 $found"
} else {
    Warn '載入不了 SketchUpAPI.dll —— 網站會起不來（DLL 是在 import 時載入的）。'
    Warn '解法一（免安裝，建議發佈時用）：到 developer.sketchup.com 下載官方 SDK，'
    Warn '        把 SketchUpAPI.dll 與 SketchUpCommonPreferences.dll 一起放到'
    Warn '        vendor\sketchup-sdk\ —— 這台機器就不必安裝 SketchUp。'
    Warn '解法二：在這台機器安裝 SketchUp（2022 以上）。'
    Warn '解法三：設環境變數 MATBOARD_SU_DLL 指向任一份 SketchUpAPI.dll。'
    Warn '若 DLL 已就位仍失敗，多半缺 Microsoft Visual C++ 2015-2022 Redistributable (x64)。'
}

# --- Front-end (optional) -------------------------------------------------
if (-not $NoWeb) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) {
        Step '建置前端'
        Push-Location (Join-Path $root 'web')
        try {
            & npm install --silent
            & npm run build
            if ($LASTEXITCODE -ne 0) { Warn '建置失敗，先沿用 web\dist 裡已建好的版本。' }
            else { Ok '完成' }
        } finally { Pop-Location }
    } else {
        Step '前端'
        Ok '沒有 Node.js —— 直接用 web\dist 裡已建好的版本（要改前端才需要裝 Node 18+）'
    }
}

Write-Host "`n設定完成。雙擊「開啟建材彙整.cmd」啟動網站。" -ForegroundColor Green
