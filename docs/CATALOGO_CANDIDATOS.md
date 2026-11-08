# Base persistente de candidatos — Etapa 1

Atualizacao Etapa2: 004/005 aplicadas no principal apos backup; fila integrada ao
scheduler e seis produtos associados. Consulte [ROTACAO_CATALOGO.md](ROTACAO_CATALOGO.md).
As secoes abaixo preservam o desenho e a validacao historica da Etapa1; suas
pendencias de ativacao foram superadas onde indicado na documentacao da Etapa2.

Implementada sem integrar ou modificar scheduler, API, RabbitMQ, publisher ou
worker. Nao possui HTTP, descoberta, loop, CLI de coleta ou tarefas no import.
A migracao 004 foi validada somente em `hunter_test:55432`; **nao aplicar no
principal sem nova autorizacao**. Nao ha seed nem importacao dos seis produtos.

## Estruturas e integridade

- `hunter_catalog_sources`: codigo estavel, loja, integracao, estado, hosts exatos,
  intervalo de 6h a 7 dias, limite de 1 a 6 e espera entre requisicoes. Nasce
  `disabled`. Nao armazena credenciais, DSNs ou tokens.
- `hunter_catalog_candidates`: fonte, URL original publica e canonica, identidade
  externa/vendedor/variante, origem, estado, contadores, datas, erro enumerado,
  produto associado opcional e lease (UUID, dono e validade).
- `hunter_catalog_runs`: UUID igual ao token da reserva, candidato, timestamps
  TIMESTAMPTZ, resultado, HTTP status, contagem de observacoes e erro enumerado.
  Datas representam instantes UTC; sua exibicao acompanha timezone da sessao.

FKs usam comportamento restritivo padrao, sem cascade. Indices cobrem identidade
externa parcial, fonte/URL, elegibilidade, estado, produto e historico de execucoes.
Uma execucao aberta por candidato; lease completo ou inteiramente nulo. Contadores
e codigos HTTP possuem checks. A migracao nao altera tabelas anteriores.

`messaging.migrate` aceita `--version 004`, exige a 003 registrada e continua com
default 002. Mantem transacao, advisory lock e verificacao de checksum. Bootstrap
de testes aplica 002/003/004 somente apos `require_isolated` validar banco e broker.

## Uso explicito do repositorio

`catalog_expansion.repository.CandidateRepository(conn)` recebe uma conexao
asyncpg existente. Cada consumidor concorrente precisa de sua propria conexao.

- `create_source(...)`: cria fonte desabilitada; rejeita hosts com URL/credenciais.
- `add(source_id, url, ...)`: valida host/HTTPS, deduplica e associa produto
  existente da mesma loja. Nao cria produto, preco ou observacao.
- `list(state=None, eligible=False, limit=100)`: consulta paginada por limite;
  elegibilidade exige fonte habilitada, estado processavel, prazo e lease vencido.
- `transition(id, state, reason=None)`: transicao administrativa validada; nao
  permite alterar candidato reservado. Rejeicao exige motivo enumerado.
- `claim(owner, limit=1, lease_seconds=300)`: reserva no maximo seis candidatos
  com `FOR UPDATE OF c SKIP LOCKED`, incrementa tentativas, inicia registro de
  execucao e fixa proxima elegibilidade em pelo menos seis horas.
- `finish(id, token, result, ...)`: valida token e validade apos obter lock;
  resultado atrasado nao pode substituir o do novo dono. Atualiza execucao e
  candidato atomicamente; nao grava observacoes, apenas sua contagem informada.
- `runs(id)`: consulta registros datados, com limite de ate 500.

As operacoes abrem transacoes, que viram savepoints se o chamador ja estiver em
transacao. Futuramente, observacoes e `finish` poderao participar da mesma
transacao externa. Nunca manter essa transacao durante HTTP.

## Identidade e estados

URLs normalizam host, porta HTTPS padrao, fragmento e parametros conhecidos de
tracking. Query de vendedor/variante e parametros desconhecidos sao preservados;
queries com nomes de credenciais sao recusadas. Nao aceitar URLs assinadas.
Somente fornecer URLs publicas; essa validacao nao substitui revisar a fonte.
Slugs distintos deduplicam quando o chamador fornece o mesmo identificador
externo verificado, vendedor e variante. Nao ha inferencia por nome, extracao
automatica de SKU ou cadastro de aliases nesta etapa. Conflitos entre URL e
identidade exigem revisao; nao mesclam nem descartam candidatos existentes.

Estados administrativos:

| Origem | Destinos |
|---|---|
| pending, active, backoff | paused, rejected, blocked |
| blocked | pending, paused, rejected |
| paused | pending, rejected |
| rejected | pending |

`finish`: success -> active; failed -> backoff; blocked -> blocked.
Execucoes abandonadas sao marcadas expired quando uma nova reserva elegivel as
recupera; o registro antigo permanece. Expiracao sozinha nao antecipa as seis
horas. Nao ha rotina automatica de recuperacao nem heartbeat implementado.
Erros sao codigos fechados (timeout, network, http_error, access_denied,
rate_limited, invalid_data, lease_expired, manual_rejection); texto livre,
excecoes e corpos HTTP nunca sao armazenados pelo repositorio.

## Validacao isolada

Em terminal de teste:

```powershell
. .\scripts\queue_environment.ps1 -Test
.venv\Scripts\python.exe -B -m messaging.testing
.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_catalog_candidates.py -v
.\scripts\test_queue.ps1
```

Os testes usam rollback para fixtures comuns. Testes concorrentes precisam de
fixtures commitadas, que permanecem apenas no banco isolado, com fontes
desabilitadas ao terminar. Nenhuma limpeza destrutiva foi adicionada.

## Limites e proxima aprovacao

Limites por fonte sao metadados para a futura etapa de execucao: nao ha mecanismo
de quota HTTP/token bucket, Retry-After, rotacao ou ativacao. `claim` limita seu
lote a seis, mas nao representa autorizacao de rede nem quota global por periodo.
Fontes habilitadas em testes nao devem ser tratadas como autorizacao comercial.
Nao foram adicionados endpoints nem novas lojas ao CHECK do catalogo 003.

Permanecem para aprovacao separada: revisao/aplicacao principal com backup,
admissao dos seis IDs sem duplicacao e preservando cooldowns, observabilidade
operacional, rotacao, permissoes das fontes, conectores e matching entre lojas.
