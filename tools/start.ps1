# Starts the Matboard server if it is not already up, then opens the browser.
#
# Safe to run repeatedly: an existing server is reused rather than a second one
# started, because two uvicorn processes on the same port would leave whichever
# lost the race silently dead.

[CmdletBinding()]
param(
    [int]$Port = 8000,
    # Used by the autostart shortcut: bring the server up without stealing focus.
    [switch]$NoBrowser,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$url = "http://127.0.0.1:$Port/"

function Say($msg) { if (-not $Quiet) { Write-Host $msg } }

function Test-Listening {
    param([int]$Port)
    $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

# Confirms it is our server on that port, not something else that happened to
# grab it - starting a second uvicorn in that case would just fail silently.
function Test-Ours {
    param([int]$Port)
    try {
        return [bool](Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3).ok
    } catch { return $false }
}

# The project can live on a network share that is not mounted yet at login.
for ($i = 0; $i -lt 30 -and -not (Test-Path $root); $i++) { Start-Sleep -Seconds 2 }
if (-not (Test-Path $root)) {
    Say "找不到專案資料夾：$root"
    exit 1
}

# Usable means: it starts, and it has the dependencies. A .venv that came along
# with a copied folder satisfies Test-Path but cannot start at all, and without
# this check uvicorn dies instantly while the wait below burns three minutes
# before admitting it. `import uvicorn` is the cheapest proof of both.
function Test-Runtime {
    param([string]$exe)
    if (-not (Test-Path $exe)) { return $false }
    try {
        $null = & $exe -c 'import uvicorn' 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

# The bundled runtime comes first: it is self-contained, so a machine with no
# Python installed at all still starts by double-clicking. .venv is the path for
# anyone who ran setup.cmd against their own Python.
$python = $null
foreach ($candidate in (Join-Path $root 'runtime\python.exe'),
                       (Join-Path $root '.venv\Scripts\python.exe')) {
    if (Test-Runtime $candidate) { $python = $candidate; break }
}
if (-not $python) {
    Say "找不到可用的 Python 環境。請執行 setup.cmd。"
    exit 1
}

if (Test-Listening -Port $Port) {
    if (Test-Ours -Port $Port) {
        Say "伺服器已在執行中。"
    } else {
        Say "連接埠 $Port 已被其他程式占用，請先關閉它，或改用其他連接埠。"
        exit 1
    }
} else {
    $logs = Join-Path $root 'logs'
    if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }

    Say "啟動伺服器..."
    Start-Process -FilePath $python `
        -ArgumentList '-m', 'uvicorn', 'server.app:app', '--host', '127.0.0.1', '--port', $Port `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs 'server.out.log') `
        -RedirectStandardError  (Join-Path $logs 'server.err.log')

    # Loading Python plus numpy and reportlab off a network share takes the best
    # part of a minute on a cold cache, so this window has to be generous - a
    # short one gives up while the server is still importing and reports a
    # failure that never happened.
    $deadline = (Get-Date).AddSeconds(180)
    $ready = $false
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 800
        if (Test-Ours -Port $Port) { $ready = $true; break }
    }
    if (-not $ready) {
        Say "伺服器在 180 秒內沒有回應。最後的記錄："
        foreach ($f in 'server.err.log', 'server.out.log') {
            $log = Join-Path $logs $f
            if (Test-Path $log) { Get-Content $log -Tail 12 | ForEach-Object { Say "  $_" } }
        }
        exit 1
    }
    Say ("伺服器已啟動（{0:N0} 秒）。" -f $sw.Elapsed.TotalSeconds)
}

if (-not $NoBrowser) {
    Say "開啟 $url"
    Start-Process $url
}
