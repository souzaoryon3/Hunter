# Acesso administrativo interativo, sem imprimir ou persistir senha em texto.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Security
$hunterRoot=Split-Path -Parent $PSScriptRoot
$hunterBytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $hunterRoot '.secrets\administrator.dpapi')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
$hunterAdmin=[Text.Encoding]::UTF8.GetString($hunterBytes) | ConvertFrom-Json
$hunterUri=[Uri]$hunterAdmin.DATABASE_URL
if ($hunterUri.Host -notin @('localhost','127.0.0.1') -or $hunterUri.Port -ne 5432 -or $hunterUri.AbsolutePath -ne '/hunter_db') {throw 'Destino administrativo divergente.'}
$hunterPrevious=$env:PGPASSWORD
try {
    $env:PGPASSWORD=[Uri]::UnescapeDataString($hunterUri.UserInfo.Split(':',2)[1])
    & 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -X -h $hunterUri.Host -p 5432 -U postgres -d hunter_db
} finally {
    $env:PGPASSWORD=$hunterPrevious
    [Array]::Clear($hunterBytes,0,$hunterBytes.Length)
    Remove-Variable hunterAdmin,hunterUri,hunterBytes
}
