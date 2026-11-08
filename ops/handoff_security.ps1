# Handoff autorizado para aplicar as novas credenciais, sem duplicar schedulers.
$ErrorActionPreference='Stop'
$hunterRoot=Split-Path -Parent $PSScriptRoot
. "$hunterRoot\scripts\queue_environment.ps1"
$hunterInventory=Join-Path $env:TEMP 'HunterRuntime\processes.json'
$hunterState=Get-Content -LiteralPath $hunterInventory -Raw | ConvertFrom-Json
$hunterTrees=@{}
foreach ($hunterRole in @('scheduler','worker','api')) {
    $hunterExpected=@{scheduler='-m messaging.scheduler';worker='-m messaging.worker';api='-m uvicorn app:app'}[$hunterRole]
    $hunterId=[int]$hunterState.$hunterRole
    $hunterProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$hunterId"
    if (-not $hunterProcess -or -not $hunterProcess.CommandLine.Contains($hunterRoot) -or -not $hunterProcess.CommandLine.Contains($hunterExpected)) {throw 'Identidade de processo divergente; handoff recusado.'}
    $hunterChildren=@(Get-CimInstance Win32_Process -Filter "ParentProcessId=$hunterId" | Where-Object {$_.Name -ne 'conhost.exe'})
    foreach ($hunterChild in $hunterChildren) {if (-not $hunterChild.CommandLine.Contains($hunterExpected)) {throw 'Filho inesperado; handoff recusado.'}}
    $hunterTrees[$hunterRole]=@($hunterChildren.ProcessId)+@($hunterId)
}
# Recusa interrupcao durante coleta externa. Conexao dedicada segura o lock ate o fim.
$hunterPython=Join-Path $hunterRoot '.venv\Scripts\python.exe'
$hunterLockLog=Join-Path $env:TEMP ('HunterRuntime\security-lock-'+[Guid]::NewGuid().ToString('N'))
# O chamador Python segura o lock; este script nao pode ser executado isoladamente.
if ($env:HUNTER_SECURITY_HANDOFF -ne '1') {throw 'Use scripts/security_handoff.py para obter lock.'}
Stop-Process -Id $hunterTrees.scheduler -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
# Sem publisher concorrente, aguarda somente ACKs pendentes antes de trocar worker.
$hunterAdminPath=Join-Path $hunterRoot '.secrets\administrator.dpapi'
$hunterAdminBytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($hunterAdminPath),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
$hunterAdmin=[Text.Encoding]::UTF8.GetString($hunterAdminBytes) | ConvertFrom-Json
$hunterPair=$hunterAdmin.RABBIT_ADMIN_USER+':'+$hunterAdmin.RABBIT_ADMIN_PASSWORD
$hunterAuth=[Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($hunterPair))
for ($hunterTry=0;$hunterTry -lt 20;$hunterTry++) {
    $hunterQueues=Invoke-RestMethod -Uri 'http://127.0.0.1:15672/api/queues/hunter' -Headers @{Authorization="Basic $hunterAuth"}
    $hunterPending=($hunterQueues | Measure-Object -Property messages_unacknowledged -Sum).Sum
    if ($hunterPending -eq 0) {break}
    Start-Sleep -Seconds 1
}
if ($hunterPending -ne 0) {throw 'Worker ainda possui mensagens sem ACK; revisar antes de interromper.'}
foreach ($hunterRole in @('worker','api')) {Stop-Process -Id $hunterTrees[$hunterRole] -ErrorAction SilentlyContinue}
Start-Sleep -Seconds 2
foreach ($hunterRole in @('scheduler','worker','api')) {foreach ($hunterId in $hunterTrees[$hunterRole]) {if (Get-Process -Id $hunterId -ErrorAction SilentlyContinue) {throw 'Processo antigo ainda ativo.'}}}
$env:HUNTER_SCAN_SECONDS='10'
# Nenhuma credencial administrativa/de teste e herdada pelos processos de runtime.
Remove-Item Env:MIGRATION_DATABASE_URL,Env:PGPASSWORD,Env:HUNTER_RABBIT_PASSWORD,Env:HUNTER_TEST_DB_PASSWORD,Env:HUNTER_TEST_JWT_SECRET,Env:HUNTER_MAIN_JWT_SECRET -ErrorAction SilentlyContinue
[Array]::Clear($hunterAdminBytes,0,$hunterAdminBytes.Length)
Remove-Variable hunterAdmin,hunterAdminBytes,hunterPair,hunterAuth
$hunterStamp=Get-Date -Format 'yyyyMMdd_HHmmss'
foreach ($hunterRole in @('api','worker','scheduler')) {
    $hunterArguments=if ($hunterRole -eq 'api') {@('-B','-m','uvicorn','app:app','--host','127.0.0.1','--port','8000')} else {@('-B','-m',"messaging.$hunterRole")}
    $hunterLog=Join-Path $env:TEMP "HunterRuntime\$hunterRole-security-$hunterStamp"
    $hunterNew=Start-Process -FilePath $hunterPython -ArgumentList $hunterArguments -WorkingDirectory $hunterRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$hunterLog.log" -RedirectStandardError "$hunterLog.err.log"
    $hunterState.$hunterRole=$hunterNew.Id
}
$hunterState | ConvertTo-Json | Set-Content -LiteralPath $hunterInventory -Encoding UTF8
Write-Host "Handoff concluido: API=$($hunterState.api), worker=$($hunterState.worker), scheduler=$($hunterState.scheduler); frontend preservado."
