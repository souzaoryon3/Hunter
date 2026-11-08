# Seguranca final e simulacao local — 07/11/2026

## Resultado confirmado

Principal hunter_db:5432 preservado: seis produtos KaBuM, seis imagens,12 observacoes
e seis candidatos; fingerprint de produtos/historico igual ao backup. Migracoes
002/003/004/005 conferidas, sem alterar SQL ou aplicar nova migracao.

- `hunter_app` herda somente `hunter_runtime`: DML necessario aos processos;
  sem superuser, createdb, createrole, replication, bypassrls, ownership ou CREATE
  no schema public. Historico e logs de processamento permitem SELECT/INSERT,
  sem UPDATE/DELETE/TRUNCATE. CRUD de usuarios inclui auditoria invoker/sequence.
- `hunter_migration` e membro de `hunter_owner`: ownership dos objetos
  public transferido explicitamente, sem REASSIGN OWNED global. Novas tabelas
  exigem revisao explicita de grants; runtime nao recebe DML universal por default.
  A verificacao final observou current_user=hunter_migration; nao presumir que
  conexoes de ferramentas executam automaticamente SET ROLE hunter_owner.
- Senha administrativa postgres e JWT rotacionados. Senha antiga foi recusada
  por psql; token antigo recebe401. Isso tambem exige atualizar credenciais salvas
  do pgAdmin e qualquer uso de postgres no banco local projeto1, sem alterar dados.
- RabbitMQ principal: administrador com senha nova, runtime `hunter_app` sem tags
  administrativas e ACL limitada a recursos hunter.* e exchange padrao. Filas,
  mensagens e volumes preservados; um consumidor, zero pendentes na verificacao.
- API/worker/scheduler reiniciados em handoff sob lock de coleta e apos drenar
  mensagens sem ACK. Frontend preservado. Credenciais administrativas, de migracao
  e de teste removidas do ambiente dos processos iniciados pelo handoff.

## Cofres e operacao

Segredos ativos principais estao em `.secrets/*.dpapi`, cifrados com DPAPI
CurrentUser do operador Windows, ignorados por Git/Docker e com ACL privada.
`runtime.dpapi`, `migration.dpapi` e `administrator.dpapi` separam os papeis.
Nao copiar esses arquivos como configuracao portavel de Azure. Use Key Vault/
injecao de segredos no ambiente de destino. Senhas antigas em arquivos ignorados
nao sao mais validas no principal; o ambiente de teste independente foi preservado.

```powershell
# Terminal do mesmo usuario Windows, sem imprimir variaveis:
. .\scripts\queue_environment.ps1
# Somente quando houver operacao administrativa autorizada:
. .\scripts\queue_environment.ps1 -Administrative
# Acesso psql administrativo, sem exibir senha:
.\scripts\admin_psql.ps1
# Verificacao somente leitura apos rotacao:
.venv\Scripts\python.exe scripts/manual/verify_security.py
```

No sandbox Codex, acessar o cofre do operador exige execucao aprovada fora do
sandbox. Cofres foram reencapsulados para esse operador; nao dependem da conta
temporaria do sandbox. Chaves TLS locais precisam existir em arquivos para os
servidores, com ACL privada; somente o CA publico e montado nos clientes.

`security_stage.py prepare/apply/broker` e `security_activate.ps1` sao procedimentos
explicitos de uso unico, com checkpoints. **Nao repetir a rotacao ja concluida.**
Provisionamento recusa login existente. `security_handoff.py` pode ser usado para
troca planejada de processos, verificando PID/comando, lock e ACKs antes de parar.

Backup custom criado antes da mudanca:
`%TEMP%/HunterBackups/hunter_pre_stage2_20261107_214920.dump`,300015 bytes,
SHA256 `c2dce158398bfb802b14cf40929218e8b3274b557d43a2658b03c45823881046`.
pg_restore --list aprovado e restauracao efetiva testada em hunter_sim:55433.
Backup contem dados pessoais: manter protegido e nao anexar/versionar.
Recovery completo anterior: `%LOCALAPPDATA%/HunterRecovery/security-before-5ad57ba18e0c47149eb5db730cf24ace.dpapi`,
379 arquivos/3609600 bytes antes da cifragem; reencapsulado e verificado para o
operador. Restaurar primeiro em diretorio novo; nao recuperar credenciais antigas
como se ainda fossem validas. Nenhuma transferencia em texto puro foi persistida.

## Stack de simulacao

`compose.simulation.yaml` reutiliza os servicos de `compose.app.yaml` e acrescenta
PostgreSQL/RabbitMQ exclusivos. Projeto Docker `hunter-simulation`, volumes
`simulation_postgres` e `simulation_rabbitmq`, sem volumes do principal.

| Componente | Acesso/localizacao |
|---|---|
| Frontend HTTPS e API via proxy | https://localhost:8443 |
| API | api:8000, sem porta publica |
| PostgreSQL copiado hunter_sim | 127.0.0.1:55433 |
| RabbitMQ AMQPS | 127.0.0.1:55671 |
| Management RabbitMQ | 127.0.0.1:55673, somente loopback |
| worker / scheduler | Processos separados; scheduler unico por banco |

Todos os seis containers ficaram running; API, PostgreSQL e RabbitMQ healthy.
HUNTER_ENV=production, PostgreSQL verify-full, AMQPS e CORS HTTPS explicito.
TCP PostgreSQL sem TLS e CA desconhecida foram recusados. Servidores usam CA
local de90 dias; navegador de teste teve excecao limitada ao contexto para CA
nao instalada no Windows. Requests/asyncpg validaram a CA normalmente; nao
desabilitar verificacao TLS na configuracao de producao.

Coleta externa permanece DESATIVADA na copia. Catalogo copiado conserva dados
reais; usuarios/alertas de smoke sao sinteticos exclusivamente nessa copia e nao
criam produtos/precos ficticios. O scheduler da copia tem DB e broker proprios,
portanto nao concorre nem publica no principal. Dados pessoais copiados exigem
os mesmos cuidados de acesso; esta stack e local e nao deve ser exposta na rede.

```powershell
# Stack ja preparada e restaurada: nao repetir prepare/restore.
. .\scripts\simulation_environment.ps1
docker compose -f compose.simulation.yaml --profile app ps
.venv\Scripts\python.exe scripts/simulate_production.py status
# Retomar os containers existentes, sem remover volumes:
docker compose -f compose.simulation.yaml --profile app up -d --wait
# Validacao somente no ambiente de simulacao:
.venv\Scripts\python.exe tests/browser_simulation.py
```

Em instalacao NOVA: prepare, infra, restore e up de simulate_production.py;
prepare recusa cofre existente e restore recusa banco nao vazio. Docker Compose
precisa suportar extends e !override. Nunca usar down -v/clean/reset neste projeto.

## Testes e pendencias

Regressao completa:121 testes aprovados (115 anteriores +6 de seguranca), sem
skips, mais demo real de ACK/retry/DLQ/idempotencia e Edge desktop/mobile.
Smoke da copia validou cadastro/login, seis imagens/API, seis historicos,
analytics, feedback, scheduler/publisher/worker/notificacao/leitura. Edge confirmou
login real, seis imagens decodificadas na busca e dashboard real6/12/mobile.
Ruff, AST e sintaxe JavaScript aprovados. A primeira ACL RabbitMQ recusou a DLX;
incluido amq.default explicitamente e repetida a entrega com sucesso.

Nao houve coleta externa forcada, exclusao de dados/filas/volumes, commit, push
ou deploy. CI remoto nao executado. Principal nativo continua com transportes de
loopback locais; nao foi convertido para acesso externo. Azure ainda requer
recursos/rede, certificados publicos, cofre externo, backups/retencao,
observabilidade e avaliacao de CSP/localStorage/rate limiting/dependencias.
