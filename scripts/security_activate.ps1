# Executar somente depois da validacao bem-sucedida da copia isolada.
$ErrorActionPreference='Stop'
. "$PSScriptRoot\queue_environment.ps1"
$hunterPython=Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
& $hunterPython "$PSScriptRoot\security_stage.py" apply
if ($LASTEXITCODE -ne 0) {throw 'Roles/rotacao nao concluidas; handoff nao executado.'}
& $hunterPython "$PSScriptRoot\security_stage.py" broker
if ($LASTEXITCODE -ne 0) {throw 'Broker nao rotacionado; conferir cofre antes de handoff.'}
& $hunterPython "$PSScriptRoot\security_handoff.py"
if ($LASTEXITCODE -ne 0) {throw 'Handoff nao concluido; conferir processos antes de repetir.'}
