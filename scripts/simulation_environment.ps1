# Dot-source no terminal de simulacao; nao imprimir o ambiente nem `compose config`.
$ErrorActionPreference = 'Stop'
$hunterRoot = Split-Path -Parent $PSScriptRoot
Add-Type -AssemblyName System.Security
$hunterProtected = Join-Path $hunterRoot '.secrets\simulation.dpapi'
$hunterClear = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($hunterProtected),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
$hunterSim = [Text.Encoding]::UTF8.GetString($hunterClear) | ConvertFrom-Json
[Array]::Clear($hunterClear,0,$hunterClear.Length)
$env:HUNTER_ENV = 'production'
$env:HUNTER_COLLECTION_ENABLED = '0'
$env:DATABASE_URL = "postgresql://hunter_app:$($hunterSim.app)@postgres:5432/hunter_sim?sslmode=verify-full&sslrootcert=/run/tls/ca.crt"
$env:RABBITMQ_URL = "amqps://hunter_sim:$($hunterSim.broker)@rabbitmq:5671/hunter_sim"
$env:JWT_SECRET_KEY = $hunterSim.jwt
$env:CORS_ORIGINS = 'https://localhost:8443'
$env:SIM_POSTGRES_PASSWORD = $hunterSim.admin
$env:SIM_RABBIT_ADMIN_PASSWORD = $hunterSim.broker_admin
$env:HUNTER_SIM_TLS = (Join-Path $hunterRoot '.secrets\simulation-tls').Replace('\','/')
Remove-Item Env:HUNTER_QUEUE_TESTS,Env:HUNTER_TEST_DATABASE_URL,Env:MIGRATION_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Variable hunterSim,hunterClear
Write-Host 'Ambiente exclusivo de simulacao carregado; segredos omitidos.'
