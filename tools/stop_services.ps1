$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$statePath = Join-Path $projectRoot '.pbl4-run\services.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No owned services recorded.'; exit 0 }
$entries = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $statePath -Raw)
foreach ($entry in $entries) {
    $child = Get-Process -Id $entry.Pid -ErrorAction SilentlyContinue
    if ($null -eq $child) { continue }
    if ($child.StartTime.ToUniversalTime().ToString('o') -ne $entry.Started -or $child.Path -ne $entry.Python) {
        throw "Refusing to stop reused/unrecognized PID $($entry.Pid)"
    }
    $child.Kill()
    if (-not $child.WaitForExit(5000)) { throw "Timed out stopping owned PID $($child.Id)" }
    Write-Output "$($entry.Name): stopped owned PID $($child.Id)"
}
Remove-Item -LiteralPath $statePath
Write-Output 'Web and MariaDB containers remain running.'
