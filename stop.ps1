# Force-stop any leftover Disease360 service processes by port.
# Usage:  .\stop.ps1
$ErrorActionPreference = "SilentlyContinue"
$ports = 8001, 8002, 5173, 5174
foreach ($port in $ports) {
    $owners = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
              Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $owners) {
        Write-Host ":$port free"
        continue
    }
    foreach ($pidToKill in $owners) {
        try {
            $name = (Get-Process -Id $pidToKill).ProcessName
            Stop-Process -Id $pidToKill -Force -ErrorAction Stop
            Write-Host ":$port killed $name (PID $pidToKill)"
        } catch {
            Write-Host ":$port PID $pidToKill already gone"
        }
    }
}
