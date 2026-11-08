# Troca local somente apos validacao isolada. Preserva antigos em backup fora do repo.
$ErrorActionPreference = 'Stop'
$hunterRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$hunterInventory = Join-Path $env:TEMP 'HunterRuntime\processes.json'
$hunterState = Get-Content -LiteralPath $hunterInventory -Raw | ConvertFrom-Json
$hunterId = [int]$hunterState.frontend
$hunterProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$hunterId"
if (-not $hunterProcess -or -not $hunterProcess.CommandLine.Contains($hunterRoot) -or
        -not $hunterProcess.CommandLine.Contains('serve_frontend.py')) { throw 'Frontend nao identificado; recusa parada.' }
$hunterChildren = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$hunterId")
foreach ($hunterChild in $hunterChildren) {
    if ($hunterChild.Name -ne 'conhost.exe' -and -not $hunterChild.CommandLine.Contains('serve_frontend.py')) {
        throw 'Filho inesperado; recusa parada.'
    }
}
$hunterNames = @('index.html','buscar.html','alertas.html','login.html','configurar.html','feedback.html','dashboard.html','ui.js','dashboard.js','ui.css','styles.css','img','imgfeature')
$hunterSources = @()
foreach ($hunterName in $hunterNames) {
    $hunterSource = (Resolve-Path (Join-Path $hunterRoot $hunterName)).Path
    if (-not $hunterSource.StartsWith($hunterRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Origem fora do projeto.' }
    $hunterSources += $hunterSource
}
foreach ($hunterPage in @('index.html','buscar.html','alertas.html','login.html','configurar.html','feedback.html','dashboard.html')) {
    if (-not (Test-Path -LiteralPath (Join-Path $hunterRoot "frontend\$hunterPage"))) { throw 'Nova pagina ausente.' }
}
$hunterArchiveRoot = [IO.Path]::GetFullPath((Join-Path $env:TEMP 'HunterRecovery'))
$hunterArchive = [IO.Path]::GetFullPath((Join-Path $hunterArchiveRoot ('frontend-originals_'+[guid]::NewGuid().ToString('N'))))
if (-not $hunterArchive.StartsWith($hunterArchiveRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Backup fora do destino previsto.' }
[IO.Directory]::CreateDirectory($hunterArchive) | Out-Null
$hunterStopIds = @($hunterId)+@(($hunterChildren | Where-Object { $_.Name -ne 'conhost.exe' }).ProcessId)
Stop-Process -Id $hunterStopIds -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
foreach ($hunterStopped in $hunterStopIds) {
    if (Get-Process -Id $hunterStopped -ErrorAction SilentlyContinue) { throw 'Frontend antigo ainda ativo; recusa mover arquivos.' }
}
foreach ($hunterSource in $hunterSources) {
    $hunterDestination = Join-Path $hunterArchive ([IO.Path]::GetFileName($hunterSource))
    if (Test-Path -LiteralPath $hunterDestination) { throw 'Destino existente; recusa sobrescrever.' }
    Move-Item -LiteralPath $hunterSource -Destination $hunterDestination
}
$hunterPython = Join-Path $hunterRoot '.venv\Scripts\python.exe'
$hunterStamp = Get-Date -Format yyyyMMdd_HHmmss
$hunterLogRoot = Join-Path $env:TEMP 'HunterRuntime'
$hunterNew = Start-Process -FilePath $hunterPython -ArgumentList @('-B','serve_frontend.py') -WorkingDirectory $hunterRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $hunterLogRoot "frontend-organized-$hunterStamp.log") -RedirectStandardError (Join-Path $hunterLogRoot "frontend-organized-$hunterStamp.err.log")
$hunterState.frontend = $hunterNew.Id
$hunterState | ConvertTo-Json | Set-Content -LiteralPath $hunterInventory -Encoding UTF8
Start-Sleep -Seconds 2
if ((Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5500/index.html' -TimeoutSec 10).StatusCode -ne 200) { throw 'Validar frontend e usar backup se necessario.' }
Write-Output "Frontend atualizado PID=$($hunterNew.Id); originais preservados em $hunterArchive. API/scheduler/worker/RabbitMQ preservados."
