param([switch]$AIOnly)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$projectRoot = Split-Path $PSScriptRoot -Parent
$aiRoot = Join-Path $projectRoot 'pbl4-face-ai'

# Tu dong nhan dien moi truong ao (.venv-pbl4 hoac .venv)
$taskPython = Join-Path $aiRoot '.venv-pbl4\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskPython = Join-Path $aiRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Missing virtualenv (.venv or .venv-pbl4). Follow pbl4-face-ai/docs/README.md.' }

$runRoot = Join-Path $projectRoot '.pbl4-run'
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$statePath = Join-Path $runRoot 'services.json'
$owned = @()
if (Test-Path -LiteralPath $statePath) {
    $previous = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $statePath -Raw)
    $owned = @($previous)
}

# Chi khoi dong AI Service (ESP32-CAM chay truc tiep On-Demand MJPEG Stream tren Port 81)
$services = @(@{ Name='ai'; Script=(Join-Path $aiRoot 'ai_web_service.py'); Cwd=$aiRoot; Url='http://127.0.0.1:5001/health'; Service='PBL4 Face AI Service' })

foreach ($service in $services) {
    $healthy = $false
    try { $health = Invoke-RestMethod -Uri $service.Url -TimeoutSec 2; $healthy = $health.service -eq $service.Service } catch {}
    if ($healthy) { Write-Output "$($service.Name): already running"; continue }
    foreach ($entry in @($owned | Where-Object { $_.Name -eq $service.Name })) {
        $existing = Get-Process -Id $entry.Pid -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            throw "$($service.Name) has an unresponsive recorded PID. Run tools/stop_services.ps1 and inspect logs before restarting."
        }
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stdout = Join-Path $runRoot "$($service.Name)-$stamp.out.log"
    $stderr = Join-Path $runRoot "$($service.Name)-$stamp.err.log"
    $child = Start-Process -FilePath $taskPython -ArgumentList @('-B', ('"' + $service.Script + '"')) -WorkingDirectory $service.Cwd -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $owned = @($owned | Where-Object { $_.Name -ne $service.Name })
    $owned += [pscustomobject]@{ Name=$service.Name; Pid=$child.Id; Started=$child.StartTime.ToUniversalTime().ToString('o'); Python=$taskPython }
    ConvertTo-Json -InputObject @($owned) -Depth 3 | Set-Content -LiteralPath $statePath -Encoding UTF8
    $deadline = (Get-Date).AddSeconds(25)
    do {
        Start-Sleep -Milliseconds 500
        if ($child.HasExited) { throw "$($service.Name) exited. See $stderr" }
        try { $health = Invoke-RestMethod -Uri $service.Url -TimeoutSec 2; $healthy = $health.service -eq $service.Service } catch {}
    } until ($healthy -or (Get-Date) -ge $deadline)
    if (-not $healthy) { throw "$($service.Name) is not ready. See $stderr" }
    Write-Output "$($service.Name): ready at $($service.Url) (PID $($child.Id))"
}
Write-Output 'Web/DB were not restarted by this script. Web: http://localhost:8080'
