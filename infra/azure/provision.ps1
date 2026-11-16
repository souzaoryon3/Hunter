# Provisiona a infraestrutura Azure do Hunter (idempotente; nada e apagado).
# Uso: powershell -File infra/azure/provision.ps1 [-Location eastus] [-StorageAccount nome]
# Requer: az login. Gera .env.azure.local (ignorado pelo Git) sem imprimir segredos.
param(
    [string]$ResourceGroup = "rg-hunter-entrega",
    [string]$Location = "eastus",
    [string]$StorageAccount = "",
    [string]$Workspace = "law-hunter",
    [string]$AppInsights = "appi-hunter"
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$tags = @("projeto=hunter", "finalidade=entrega-academica")

function Invoke-Az {
    $output = & az.cmd @args
    if ($LASTEXITCODE -ne 0) { throw "Falha: az $($args[0..2] -join ' ')" }
    return $output
}

Invoke-Az config set extension.use_dynamic_install=yes_without_prompt --only-show-errors | Out-Null
Invoke-Az config set core.only_show_errors=true | Out-Null

Write-Host "1/8 Grupo de recursos $ResourceGroup ($Location)"
Invoke-Az group create -n $ResourceGroup -l $Location --tags @tags -o none

Write-Host "2/8 Storage account (StorageV2, ZRS, TLS 1.2, sem acesso publico)"
if (-not $StorageAccount) {
    $StorageAccount = Invoke-Az storage account list -g $ResourceGroup --query "[?tags.projeto=='hunter'].name | [0]" -o tsv
    if (-not $StorageAccount) { $StorageAccount = "sthunter" + (Get-Random -Minimum 10000 -Maximum 99999) }
}
Invoke-Az storage account create -n $StorageAccount -g $ResourceGroup -l $Location `
    --sku Standard_ZRS --kind StorageV2 --access-tier Hot --https-only true `
    --min-tls-version TLS1_2 --allow-blob-public-access false --tags @tags -o none
$storageId = Invoke-Az storage account show -n $StorageAccount -g $ResourceGroup --query id -o tsv

Write-Host "3/8 Protecao de dados do Blob: versionamento e soft delete (14 dias)"
Invoke-Az storage account blob-service-properties update --account-name $StorageAccount -g $ResourceGroup `
    --enable-versioning true --enable-delete-retention true --delete-retention-days 14 `
    --enable-container-delete-retention true --container-delete-retention-days 14 -o none

Write-Host "4/8 Politica de ciclo de vida (backups: Cool apos 7 dias, exclusao apos 90)"
Invoke-Az storage account management-policy create --account-name $StorageAccount -g $ResourceGroup `
    --policy "@$PSScriptRoot\lifecycle-policy.json" -o none

Write-Host "5/8 Containers Blob e filas da Queue Storage"
$connection = Invoke-Az storage account show-connection-string -n $StorageAccount -g $ResourceGroup --query connectionString -o tsv
foreach ($container in "backups", "exportacoes") {
    Invoke-Az storage container create -n $container --connection-string $connection --public-access off -o none
}
foreach ($queue in "hunter-exportacoes", "hunter-exportacoes-poison") {
    Invoke-Az storage queue create -n $queue --connection-string $connection -o none
}

Write-Host "6/8 Log Analytics (retencao 30 dias, limite diario 0,5 GB) e Application Insights"
Invoke-Az monitor log-analytics workspace create -g $ResourceGroup -n $Workspace -l $Location `
    --retention-time 30 --quota 0.5 --tags @tags -o none
$workspaceId = Invoke-Az monitor log-analytics workspace show -g $ResourceGroup -n $Workspace --query id -o tsv
Invoke-Az monitor app-insights component create --app $AppInsights -g $ResourceGroup -l $Location `
    --workspace $workspaceId --application-type web --kind web --tags @tags -o none
$appId = Invoke-Az monitor app-insights component show --app $AppInsights -g $ResourceGroup --query id -o tsv
$insights = Invoke-Az monitor app-insights component show --app $AppInsights -g $ResourceGroup --query connectionString -o tsv

Write-Host "7/8 Diagnostico do Storage (Blob e Queue) enviado ao Log Analytics"
foreach ($service in "blobServices", "queueServices") {
    Invoke-Az monitor diagnostic-settings create -n "diag-hunter" --resource "$storageId/$service/default" `
        --workspace $workspaceId `
        --logs '[{\"category\":\"StorageRead\",\"enabled\":true},{\"category\":\"StorageWrite\",\"enabled\":true},{\"category\":\"StorageDelete\",\"enabled\":true}]' `
        --metrics '[{\"category\":\"Transaction\",\"enabled\":true}]' -o none
}

Write-Host "8/8 Alertas e workbook (dashboard)"
Invoke-Az monitor metrics alert create -n "hunter-api-falhas" -g $ResourceGroup --scopes $appId `
    --condition "count requests/failed > 0" --window-size 5m --evaluation-frequency 5m `
    --severity 2 --description "Requisicoes com falha na API Hunter" -o none
Invoke-Az monitor metrics alert create -n "hunter-api-lenta" -g $ResourceGroup --scopes $appId `
    --condition "avg requests/duration > 2000" --window-size 5m --evaluation-frequency 5m `
    --severity 3 --description "Tempo medio de resposta acima de 2 s" -o none
Invoke-Az monitor metrics alert create -n "hunter-storage-disponibilidade" -g $ResourceGroup --scopes $storageId `
    --condition "avg Availability < 99" --window-size 15m --evaluation-frequency 5m `
    --severity 2 --description "Disponibilidade do Storage abaixo de 99%" -o none
Invoke-Az deployment group create -g $ResourceGroup -n "hunter-workbook" `
    --template-file "$PSScriptRoot\workbook.json" `
    --parameters appInsightsId=$appId storageAccountId=$storageId workspaceId=$workspaceId -o none

$envFile = Join-Path $root ".env.azure.local"
@(
    "# Gerado por infra/azure/provision.ps1 - NAO versionar nem compartilhar.",
    "AZURE_STORAGE_CONNECTION_STRING=$connection",
    "AZURE_APPINSIGHTS_CONNECTION_STRING=$insights",
    "APPLICATIONINSIGHTS_CONNECTION_STRING=$insights"
) | Set-Content -Path $envFile -Encoding utf8
Write-Host "Concluido. Storage: $StorageAccount | App Insights: $AppInsights | segredos em .env.azure.local"
