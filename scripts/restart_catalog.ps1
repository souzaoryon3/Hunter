# Chamado pelo catalog_stage2.py restart sob lock PostgreSQL da coleta.
# Reinicia apenas API e scheduler identificados no inventario; preserva os demais.
param([switch]$SchedulerOnly,[switch]$ApiOnly)
$ErrorActionPreference = 'Stop'
if ($SchedulerOnly -and $ApiOnly) { throw 'Escolha apenas um papel para reiniciar.' }
if ($env:HUNTER_CATALOG_HANDOFF -ne '1') { throw 'Use catalog_stage2.py restart para obter o lock de coleta.' }
. "$PSScriptRoot\queue_environment.ps1"
# Cadencia de alertas principal registrada na continuidade; coleta continua 6h.
if (-not $env:HUNTER_SCAN_SECONDS) { $env:HUNTER_SCAN_SECONDS = '10' }
$hunterRoot = Split-Path -Parent $PSScriptRoot
$hunterInventory = Join-Path $env:TEMP 'HunterRuntime\processes.json'
$hunterState = Get-Content -LiteralPath $hunterInventory -Raw | ConvertFrom-Json
$hunterTargets = @()
$hunterRoles = if ($SchedulerOnly) { @('scheduler') } elseif ($ApiOnly) { @('api') } else { @('api','scheduler') }
foreach ($hunterRole in $hunterRoles) {
    $hunterId = [int]$hunterState.$hunterRole
    $hunterProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$hunterId"
    $hunterExpected = if ($hunterRole -eq 'api') { '-m uvicorn app:app' } else { '-m messaging.scheduler' }
    if (-not $hunterProcess -or -not $hunterProcess.CommandLine.Contains($hunterRoot) -or
            -not $hunterProcess.CommandLine.Contains($hunterExpected)) { throw 'PID/comando divergente; nenhuma parada autorizada.' }
    $hunterChildren = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$hunterId")
    foreach ($hunterChild in $hunterChildren) {
        if ($hunterChild.Name -eq 'conhost.exe') { continue }
        if (-not $hunterChild.CommandLine.Contains($hunterExpected)) { throw 'Filho inesperado; revisar processos.' }
    }
    $hunterTargets += @($hunterChildren | Where-Object { $_.Name -ne 'conhost.exe' }).ProcessId
    $hunterTargets += $hunterId
}
# Ambas as arvores validadas antes da primeira parada. Transacoes abertas fazem
# rollback PostgreSQL; outbox/ACK/retry existentes preservam retomada de eventos.
Stop-Process -Id $hunterTargets -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
foreach ($hunterId in $hunterTargets) {
    if (Get-Process -Id $hunterId -ErrorAction SilentlyContinue) { throw 'Processo antigo ainda ativo; nao criar duplicata.' }
}
$hunterPython = Join-Path $hunterRoot '.venv\Scripts\python.exe'
$hunterStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$hunterLogRoot = Join-Path $env:TEMP 'HunterRuntime'
if (-not $SchedulerOnly) {
    $hunterApi = Start-Process -FilePath $hunterPython -ArgumentList @('-B','-m','uvicorn','app:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $hunterRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $hunterLogRoot "api-stage2-$hunterStamp.log") -RedirectStandardError (Join-Path $hunterLogRoot "api-stage2-$hunterStamp.err.log")
    $hunterState.api = $hunterApi.Id
}
if (-not $ApiOnly) {
    $hunterScheduler = Start-Process -FilePath $hunterPython -ArgumentList @('-B','-m','messaging.scheduler') -WorkingDirectory $hunterRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $hunterLogRoot "scheduler-stage2-$hunterStamp.log") -RedirectStandardError (Join-Path $hunterLogRoot "scheduler-stage2-$hunterStamp.err.log")
    $hunterState.scheduler = $hunterScheduler.Id
}
$hunterState | ConvertTo-Json | Set-Content -LiteralPath $hunterInventory -Encoding UTF8
Write-Output "API PID=$($hunterState.api); scheduler PID=$($hunterState.scheduler). Logs stage2-$hunterStamp."
