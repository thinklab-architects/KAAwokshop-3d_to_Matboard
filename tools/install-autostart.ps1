# Registers a logon task that brings the Matboard server up in the background.
#
# A Scheduled Task rather than a Startup-folder shortcut: the task's Hidden
# setting genuinely suppresses the console, where a shortcut still flashes one,
# and the trigger can be delayed so a project on a network share has time to
# become reachable.

param([switch]$Remove, [switch]$Status)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$taskName = 'Matboard 建材彙整伺服器'

function ConvertTo-Unc([string]$path) {
    $qualifier = (Split-Path -Qualifier $path).TrimEnd(':')
    $provider = (Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${qualifier}:'" `
        -ErrorAction SilentlyContinue).ProviderName
    if ($provider) { return $path -replace "^${qualifier}:", $provider }
    return $path
}

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($Status) {
    if (-not $existing) { Write-Host "尚未設定自動啟動。"; exit 0 }
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    Write-Host "工作名稱   : $taskName"
    Write-Host "狀態       : $($existing.State)"
    Write-Host "上次執行   : $($info.LastRunTime)  結果碼 $($info.LastTaskResult)"
    exit 0
}

if ($Remove) {
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "已移除自動啟動。"
    } else {
        Write-Host "本來就沒有設定自動啟動。"
    }
    exit 0
}

$script = ConvertTo-Unc (Join-Path $root 'tools\start.ps1')
if (-not (Test-Path $script)) { throw "找不到 $script" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ("-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass " +
               "-File `"$script`" -NoBrowser -Quiet")

# Give the network share time to mount before the task fires.
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = 'PT30S'

$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description `
    '登入後在背景啟動建材彙整網站的本機伺服器 (http://127.0.0.1:8000)' -Force | Out-Null

Write-Host "已設定：登入 Windows 後 30 秒，伺服器會在背景自動啟動。"
Write-Host "網址：http://127.0.0.1:8000"
Write-Host ""
Write-Host "要取消請執行：tools\install-autostart.ps1 -Remove"
