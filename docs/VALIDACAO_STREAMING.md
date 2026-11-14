# Validacao da mineracao em streaming em 14 de novembro de 2026

Implementacao instalada na instancia local `hunter-dev-main`, em
`http://localhost:8088`. Nenhuma mudanca foi aplicada a instalacao original.

## Resultado comprovado

- Observacao nova -> outbox transacional -> RabbitMQ -> consumidor independente
  -> resultado analitico PostgreSQL -> GET /analytics/streaming.
- 205 testes automatizados aprovados, sem skips, com PostgreSQL e RabbitMQ reais
  na instancia isolada `hunter-team-test-streaming`. Cobertura global de linhas:
  83% (2853 instrucoes, 482 nao cobertas). Isso nao representa cobertura integral
  de todas as plataformas nem teste de carga.
- Demo `tests/demo_streaming.py`: processo independente, duas observacoes novas
  de fixture sintetica, precos 100 e 80, dois resultados persistidos, media 90,
  variacao -20%, queda detectada e duplicata sem resultado adicional. `replay=false`.
- Regressao de notificacoes com dois workers, ACK/retry/DLQ/idempotencia aprovada.
- Navegador: busca, login, CRUD, historico, notificacoes e dashboard real/demo,
  desktop/celular aprovados no ambiente isolado. Nao constitui cliente desktop nativo.
- Ruff, diff --check e builds Docker aprovados. CI atualizada para executar a demo;
  nenhuma execucao remota GitHub Actions foi conferida ou publicada nesta etapa.

## Conferencia da instalacao

Backup do banco da nova versao criado antes do DDL, em local privado ignorado pelo
Git. O indice do dump foi lido com pg_restore --list; restauracao completa desse
backup nao foi testada nesta etapa. Migracoes 007 e 008 aplicadas por executor
transacional com checksum, sem editar migracoes ja aplicadas. 008 reconhece as
fontes reais Scrapling anteriormente ausentes da lista do modulo analitico.

Antes e depois: 250 produtos e 300 observacoes preservados. Depois: 300 eventos
processed e 300 resultados persistidos, todos com replay=true porque representam
o historico anterior a ativacao. Nenhuma observacao ficticia foi inserida na
instalacao principal para demonstrar streaming; as fixtures ficam no teste isolado.

RabbitMQ: `hunter_dev.analytics`, um consumidor, zero mensagens ready/unacknowledged
na conferencia final; DLQ analitica vazia. Fila `.price` tambem com consumidor ativo.
HTTP 200 em index.html, docs, health/ready, analytics/streaming e estatisticas real/demo.

A API recebeu os arquivos atualizados por docker cp e foi reiniciada para preservar
o navegador efemero de coleta que ja existia no container. O consumidor analytics
usa imagem nova construida do checkout. Compose/bootstrap reproduzem a instalacao
em um proximo build; nao dependem da copia manual para instalacoes novas.
Nenhum scraper, coleta externa, remocao de dados, commit ou push executado.

## Evidencias locais

Em `local-reports/streaming-20261114`, ignorado pelo Git:

- full-suite.log: execucao final integral, cobertura e demos.
- demo-eventos-novos.json: prova do fluxo com novos eventos, fixture explicita.
- api-resultados.json: resposta da API instalada, com resultados persistidos.

Roteiro de apresentacao e SQL somente leitura em [MINERACAO_STREAMING.md](MINERACAO_STREAMING.md).
Para repetir a suite, na raiz da nova copia:

```text
python scripts/dev.py test --instance streaming
```

A configuracao `.env.team-test.streaming.local` ja existe nesta maquina e deve
ser reutilizada. Em outra maquina, executar primeiro test-configure --instance
streaming. Nao copiar senhas/arquivos locais para documentacao ou GitHub.
Os servicos de teste foram parados ao concluir, com containers e volumes preservados;
o comando test inicia-os novamente. Os servicos da aplicacao principal ficam ativos.

## Correcoes durante a validacao

O build inicial de navegador falhou por ausencia de libatomic1. Dockerfile e
Dockerfile.test agora instalam essa dependencia. A regressao tambem revelou uma
fixture antiga de rotacao sensivel a IDs acumulados e prazos muito proximos do
relogio da VM; apenas o teste foi ajustado para usar posicao ordenada e margem
temporal. Codigo de coleta, quotas e bloqueios de acesso nao foram alterados.
A suite final passou com o banco de testes reutilizado, sem apagar fixtures.

## Arquivos da entrega

Implementacao: data_mining/streaming.py, data_mining/api.py,
data_mining/repository.py, messaging/broker.py e messaging/migrate.py.

Banco/infraestrutura: migrations/007_mineracao_streaming.sql,
migrations/008_streaming_fontes_scrapling.sql, ops/bootstrap.py,
ops/dev_bootstrap.py, ops/postgres_roles.sql, compose.dev.yaml,
Dockerfile e Dockerfile.test.

Validacao/CI: tests/test_streaming.py, tests/demo_streaming.py,
tests/test_rotation.py, messaging/testing.py, scripts/run_team_tests.py
e .github/workflows/ci.yml.

Documentacao: README.md, docs/DATA_MINING.md, docs/MINERACAO_STREAMING.md,
este relatorio e CONTINUIDADE.md (preservando o registro preexistente).

## Limites

Janela por contagem e snapshots por evento, sem revisao retroativa de resultados
apos chegada tardia. Sinais estatisticos exploratorios, sem precisao preditiva
avaliada ou SLA de latencia. O K-Means anterior continua sob demanda. Consumo
continuo fica aguardando novas observacoes, mas coleta externa continua desligada.
PLN, desktop independente e Azure nao fazem parte desta entrega.
