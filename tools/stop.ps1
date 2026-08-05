# Stops the Matboard server.

param([int]$Port = 8000)

$conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $conns) {
    Write-Host "伺服器沒有在執行。"
    exit 0
}
# Not $pid - that is a PowerShell automatic variable and cannot be assigned.
foreach ($procId in ($conns.OwningProcess | Select-Object -Unique)) {
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p) {
        Stop-Process -Id $procId -Force
        Write-Host "已停止 $($p.ProcessName) (pid $procId)。"
    }
}
