# Integracao Azure (Blob, Queue Storage e monitoramento)

Integracao **opcional**: sem `.env.azure.local`, o Hunter funciona exatamente como antes.
A aplicacao continua no Docker local; armazenamento, fila e telemetria usam servicos
gerenciados do Azure (assinatura Azure for Students, regiao East US).

## Recursos (grupo `rg-hunter-entrega`)

| Recurso | Configuracao | Uso |
|---|---|---|
| Storage account (StorageV2, ZRS) | HTTPS, TLS 1.2, sem acesso publico, versionamento, soft delete 14 d | Blob + Queue |
| Containers `backups`, `exportacoes` | privados; ciclo de vida em `infra/azure/lifecycle-policy.json` | pg_dump e exportacoes do catalogo |
| Filas `hunter-exportacoes`, `hunter-exportacoes-poison` | visibilidade 120 s, ate 5 tentativas | pedidos de exportacao |
| Log Analytics `law-hunter` | retencao 30 d, limite 0,5 GB/dia | logs e KQL |
| Application Insights `appi-hunter` | baseado em workspace, amostragem 100% | API, worker e backup |
| Alertas | falhas da API, latencia > 2 s, disponibilidade do Storage < 99% | notificacao |
| Workbook "Hunter - Monitoramento do ambiente" | `infra/azure/workbook.json` | painel |

## Provisionar (idempotente)

```powershell
az login --use-device-code
powershell -ExecutionPolicy Bypass -File infra/azure/provision.ps1
```

O script cria/atualiza os recursos e grava `.env.azure.local` (ignorado pelo Git) sem
imprimir segredos. Nunca passe a connection string como argumento de linha de comando:
o `cmd` do Windows pode ecoar o valor. Para comandos `az storage`, prefira
`--account-name <conta> --auth-mode key`. Em caso de exposicao, rotacione com
`az storage account keys renew` e atualize o arquivo local.

## Operacao

```powershell
# Stack local com o worker azure-export (perfil "azure" ativado pelo dev.py)
.venv\Scripts\python.exe -B scripts/dev.py up --instance scrapling

# Fila: publica um pedido; o worker exporta o catalogo para o Blob
docker exec hunter-dev-scrapling-azure-export-1 python -B -m cloud.enqueue exportar_catalogo

# Backup do PostgreSQL para o Blob, verificacao de restauracao e listagem
.venv\Scripts\python.exe -B scripts/azure_backup.py backup --instance scrapling
.venv\Scripts\python.exe -B scripts/azure_backup.py verify --instance scrapling
.venv\Scripts\python.exe -B scripts/azure_backup.py list

# Desligar a stack local (os recursos Azure nao tem computacao ligada)
.venv\Scripts\python.exe -B scripts/dev.py stop --instance scrapling
```

Se a API for recriada sozinha, o nginx do frontend pode responder 502 ate ser reiniciado
(`docker restart hunter-dev-scrapling-frontend-1`); comportamento anterior a esta integracao.

## Codigo

- `cloud/config.py`: configuracao validada; erros nunca exibem a chave.
- `cloud/messages.py`: contrato JSON da fila (tipo, UUID, data ISO, ate 2 KB).
- `cloud/storage.py`: Blob/Queue; upload sem sobrescrita, SHA-256 nos metadados, download verificado.
- `cloud/export_worker.py`: consumidor; apaga a mensagem so apos o upload; poison apos N tentativas.
- `cloud/telemetry.py`: OpenTelemetry -> Application Insights; healthchecks fora da coleta.
- `scripts/azure_backup.py`: pg_dump no container, upload, verificacao com pg_restore.
- `tests/test_cloud.py`: testes sem rede (configuracao, contrato, exportacao, poison).

## Politica de backup (resumo)

RPO 24 h, RTO 1 h. Backup diario e antes de migracoes; verificacao semanal com
`verify`; Hot 7 d, Cool ate 90 d, exclusao automatica apos 90 d; versionamento e soft
delete de 14 dias; ZRS. O script nunca apaga backups.

## Alta disponibilidade

Implementado: ZRS, desacoplamento por fila com reprocessamento e poison, idempotencia e
DLQ do RabbitMQ, healthchecks/restart dos containers, alertas. Proposta para producao:
Container Apps com 2+ replicas em zonas, PostgreSQL Flexible Server com HA de zona,
Front Door/Application Gateway, Storage GZRS, Key Vault e identidade gerenciada.
