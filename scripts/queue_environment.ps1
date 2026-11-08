# Carregue com dot-sourcing: . .\scripts\queue_environment.ps1
# Segredos aleatórios são gerados apenas no arquivo local ignorado pelo Git.
param([switch]$Test,[switch]$Administrative)
$ErrorActionPreference = 'Stop'
if ($Test -and $Administrative) { throw 'Nao misture runtime de teste e administracao principal.' }
if (-not $Test -and ($env:HUNTER_QUEUE_TESTS -eq '1' -or
        ($env:DATABASE_URL -and ([Uri]$env:DATABASE_URL).AbsolutePath -eq '/hunter_test'))) {
    throw 'Ambiente de teste ativo. Abra um terminal novo e configure DATABASE_URL principal.'
}
$hunterRoot = Split-Path -Parent $PSScriptRoot
$hunterConfig = Join-Path $hunterRoot '.env.queue.local'
function New-HunterSecret {
    $hunterBytes = New-Object byte[] 32
    $hunterRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $hunterRng.GetBytes($hunterBytes) } finally { $hunterRng.Dispose() }
    return ([BitConverter]::ToString($hunterBytes)).Replace('-', '').ToLowerInvariant()
}
if (-not (Test-Path -LiteralPath $hunterConfig)) {
    @(
        'HUNTER_RABBIT_USER=hunter',
        ('HUNTER_RABBIT_PASSWORD=' + (New-HunterSecret)),
        ('HUNTER_TEST_DB_PASSWORD=' + (New-HunterSecret))
    ) | Set-Content -LiteralPath $hunterConfig -Encoding ASCII
}
Get-Content -LiteralPath $hunterConfig | ForEach-Object {
    if ($_ -match '^(HUNTER_RABBIT_USER|HUNTER_RABBIT_PASSWORD|HUNTER_TEST_DB_PASSWORD|HUNTER_TEST_JWT_SECRET|HUNTER_MAIN_JWT_SECRET|HUNTER_MAIN_COLLECTION_ENABLED)=(.+)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
}
$hunterUser = [Uri]::EscapeDataString($env:HUNTER_RABBIT_USER)
$hunterPassword = [Uri]::EscapeDataString($env:HUNTER_RABBIT_PASSWORD)
if ($Test) {
    $env:HUNTER_ENV = 'test'
    $env:HUNTER_COLLECTION_ENABLED = '0'
    if (-not $env:HUNTER_TEST_JWT_SECRET) {
        $env:HUNTER_TEST_JWT_SECRET = New-HunterSecret
        ('HUNTER_TEST_JWT_SECRET=' + $env:HUNTER_TEST_JWT_SECRET) | Add-Content -LiteralPath $hunterConfig -Encoding ASCII
    }
    $env:JWT_SECRET_KEY = $env:HUNTER_TEST_JWT_SECRET
    $env:RABBITMQ_URL = "amqp://${hunterUser}:${hunterPassword}@127.0.0.1:5673/hunter_test"
    $hunterDatabasePassword = [Uri]::EscapeDataString($env:HUNTER_TEST_DB_PASSWORD)
    $env:DATABASE_URL = "postgresql://hunter_test:${hunterDatabasePassword}@127.0.0.1:55432/hunter_test"
    $env:HUNTER_TEST_DATABASE_URL = $env:DATABASE_URL
    $env:MIGRATION_DATABASE_URL = $env:DATABASE_URL
    $env:HUNTER_QUEUE_TESTS = '1'
    $env:HUNTER_QUEUE_PREFIX = 'hunter_test'
    $env:HUNTER_SCAN_SECONDS = '2'
    $env:HUNTER_RETRY_SECONDS = '1'
} else {
    $hunterRuntime = Join-Path $hunterRoot '.env.runtime.local'
    if (Test-Path -LiteralPath $hunterRuntime) {
        Get-Content -LiteralPath $hunterRuntime | ForEach-Object {
            if ($_ -match '^(DATABASE_URL|MIGRATION_DATABASE_URL)=(.+)$' -and
                    -not [Environment]::GetEnvironmentVariable($matches[1], 'Process')) {
                [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
            }
        }
    }
    if (-not $env:DATABASE_URL -and -not (Test-Path -LiteralPath (Join-Path $hunterRoot '.secrets\runtime.dpapi'))) { throw 'Configure DATABASE_URL explicitamente ou no cofre local.' }
    if (-not $env:HUNTER_COLLECTION_ENABLED -and $env:HUNTER_MAIN_COLLECTION_ENABLED) {
        $env:HUNTER_COLLECTION_ENABLED = $env:HUNTER_MAIN_COLLECTION_ENABLED
    }
    if (-not $env:JWT_SECRET_KEY) {
        if (-not $env:HUNTER_MAIN_JWT_SECRET) {
            $env:HUNTER_MAIN_JWT_SECRET = New-HunterSecret
            ('HUNTER_MAIN_JWT_SECRET=' + $env:HUNTER_MAIN_JWT_SECRET) | Add-Content -LiteralPath $hunterConfig -Encoding ASCII
        }
        $env:JWT_SECRET_KEY = $env:HUNTER_MAIN_JWT_SECRET
    }
    $env:RABBITMQ_URL = "amqp://${hunterUser}:${hunterPassword}@127.0.0.1:5672/hunter"
    # DATABASE_URL existente é preservada. Configure-a explicitamente para API/worker.
}
if (-not $Test) {
    $hunterProtected = Join-Path $hunterRoot '.secrets\runtime.dpapi'
    if (Test-Path -LiteralPath $hunterProtected) {
        Add-Type -AssemblyName System.Security
        $hunterClear = [Security.Cryptography.ProtectedData]::Unprotect(
            [IO.File]::ReadAllBytes($hunterProtected), $null,
            [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $hunterValues = [Text.Encoding]::UTF8.GetString($hunterClear) | ConvertFrom-Json
        foreach ($hunterProperty in $hunterValues.PSObject.Properties) {
            if ($hunterProperty.Name -notin @('DATABASE_URL','JWT_SECRET_KEY','RABBITMQ_URL')) {
                throw 'Chave inesperada no cofre de runtime.'
            }
            [Environment]::SetEnvironmentVariable($hunterProperty.Name, [string]$hunterProperty.Value, 'Process')
        }
        [Array]::Clear($hunterClear, 0, $hunterClear.Length)
        Remove-Variable hunterValues,hunterClear
    }
    if ($Administrative) {
        $hunterMigration = Join-Path $hunterRoot '.secrets\migration.dpapi'
        $hunterClear = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($hunterMigration),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        $hunterValues = [Text.Encoding]::UTF8.GetString($hunterClear) | ConvertFrom-Json
        $env:MIGRATION_DATABASE_URL = $hunterValues.MIGRATION_DATABASE_URL
        [Array]::Clear($hunterClear,0,$hunterClear.Length)
        $hunterAdmin = Join-Path $hunterRoot '.secrets\administrator.dpapi'
        $hunterClear = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($hunterAdmin),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        $hunterValues = [Text.Encoding]::UTF8.GetString($hunterClear) | ConvertFrom-Json
        if ($hunterValues.RABBIT_ADMIN_PASSWORD) {$env:HUNTER_RABBIT_PASSWORD=$hunterValues.RABBIT_ADMIN_PASSWORD}
        [Array]::Clear($hunterClear,0,$hunterClear.Length)
        Remove-Variable hunterValues,hunterClear
    }
}
Write-Host 'Ambiente da fila carregado. Valores secretos não são exibidos.'
