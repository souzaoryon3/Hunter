$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\queue_environment.ps1" -Test
$hunterPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
& $hunterPython -B -m messaging.testing
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap do ambiente isolado falhou.' }
& $hunterPython -B -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Testes automatizados falharam.' }
& $hunterPython -B tests/demo_queue.py
if ($LASTEXITCODE -ne 0) { throw 'Demonstração automatizada de falhas falhou.' }
& $hunterPython -B tests/browser_queue.py
if ($LASTEXITCODE -ne 0) { throw 'Testes de navegador falharam.' }
& $hunterPython -B tests/browser_dashboard.py
if ($LASTEXITCODE -ne 0) { throw 'Dashboard analitico falhou.' }
