# Hunter — relatório de validação SCRUM-28 a SCRUM-33

Data: 24/10/2026. Implementação e validação concluídas no ambiente isolado.
Implantação no banco real não realizada nesta etapa.

## Resultado por história

| História | Resultado comprovado | Evidência |
|---|---|---|
| SCRUM-28 | Concluída | Detecção em `messaging/service.py`; igualdade ao alvo, preço acima, ausência de oferta, nova transição e edição testados. |
| SCRUM-29 | Concluída | Publicação real no RabbitMQ, mensagens persistentes, confirmação, outbox preservada em falha e recuperação. |
| SCRUM-30 | Concluída | Worker independente com ACK/NACK; consumo real e demonstração com dois workers concorrentes. |
| SCRUM-31 | Concluída | API, agendador e worker separados; notificação persistida e exibida no frontend autenticado. |
| SCRUM-32 | Concluída | Logs de confirmação, processamento, duplicatas, retry e DLQ; status, tentativas e horários validados. |
| SCRUM-33 | Concluída | Falha simulada, três tentativas, DLQ confirmada, idempotência, quarentena e recuperação após reinício. |

Conclusão limitada ao escopo implementado: notificações dentro do Hunter sobre o
catálogo armazenado. Não inclui envio de e-mail, atualização de preços ou operação
de produção com alta disponibilidade.

## Execuções e resultados

1. `python -B -m unittest discover -s tests -v`: 26 testes aprovados, sem skips.
2. `python -B tests/demo_queue.py`: aprovado. Dois workers reais, mesmo evento
   publicado duas vezes, uma notificação, evento de falha em três tentativas e DLQ.
3. `scripts/test_queue.ps1`: aprovado integralmente, incluindo os mesmos 26 testes,
   nova demonstração e `tests/browser_queue.py`.
4. Navegador Edge: cadastro/login reais, criação de alerta, detecção pelo agendador,
   publicação, consumo, notificação, marcação como lida e persistência após recarga.
   Regressão de busca, filtros, paginação, perfil, feedback e alertas em seis páginas
   e dois tamanhos de tela também aprovada.
5. `tests/restart_queue.py prepare` → reinício dos containers existentes → `verify`:
   aprovado. Eventos publicados sobreviveram no broker; entrega sem ACK recuperada;
   retry e outbox retomados; quatro notificações únicas. Os dois primeiros eventos
   foram consumidos antes de qualquer republicação, comprovando persistência no broker.
6. Revisão de whitespace com `git diff --check`: sem erros; avisos LF/CRLF do Git
   são relativos à configuração de finais de linha do Windows.

Os logs de teste foram observados nesta sessão; este relatório registra os resultados
sem copiar credenciais ou tokens. Fixtures históricas anteriores à correção dos
relógios foram preservadas, sem reescrever dados. Novos registros usam o relógio
do PostgreSQL e têm ordenação temporal coberta por teste.

## Segurança e preservação

- Docker Desktop retomado, containers de teste existentes iniciados com `start`.
- Serviços usados: `postgres-test` (55432) e `rabbitmq-test` (5673/15673).
- Volumes preservados: `hunter-queue_postgres_test_data` e `hunter-queue_rabbitmq_test_data`.
- Nenhum banco, tabela ou volume existente foi apagado ou recriado. Nenhum purge.
- Apenas fixtures sintéticas no ambiente isolado; testes transacionais usam rollback.
- Migração 002 conferida pelo script exclusivamente no banco de teste.
- Nenhuma migração ou modificação de dados no banco real. Nenhum scraper executado.
- Segredos permanecem em variáveis de ambiente/arquivos locais ignorados; nada foi
  exibido no relatório. Não houve commit, push, reset ou descarte de alterações.

## Arquivos da Sprint

Criados na implementação:

- `compose.yaml`.
- `messaging/__init__.py`, `broker.py`, `catalog.py`, `config.py`, `demo.py`,
  `migrate.py`, `runtime.py`, `scheduler.py`, `service.py`, `testing.py`, `worker.py`.
- `migrations/002_alertas_assincronos.sql`.
- `scripts/queue_environment.ps1`, `scripts/test_queue.ps1`.
- `tests/test_queue.py`, `tests/demo_queue.py`, `tests/browser_queue.py`.
- `docs/FILA_RABBITMQ.md`.

Modificados na implementação: `app.py`, `alertas.html`, `ui.js`, `requirements.txt`,
`README.md`, `.gitignore`, `.dockerignore` e `tests/browser_ux.py`.

Nesta etapa de finalização/validação:

- Criados: `tests/restart_queue.py` e este relatório.
- Modificados: `tests/test_queue.py` (preservar filas temporárias), `.gitignore` e
  `.dockerignore` (referência local do teste de recuperação), `docs/FILA_RABBITMQ.md`
  e `CONTINUIDADE.md`.
- Arquivos locais ignorados gerados pelos testes não são parte da entrega versionável.
- Mudanças anteriores de JWT, frontend e Pichau foram preservadas.

## Roteiro para apresentação

Siga [FILA_RABBITMQ.md](FILA_RABBITMQ.md), que inclui os comandos de RabbitMQ, API,
frontend, worker e agendador, além de duplicidade, falha simulada e recuperação.
Para validação automatizada: carregue o ambiente com
`. .\scripts\queue_environment.ps1 -Test`, inicie os containers existentes e execute
`.\scripts\test_queue.ps1`. Não execute o teste de reinício simultaneamente à suíte.

## Pendências e limites

- Aplicação no banco real e configuração de execução contínua ficam para implantação
  autorizada posterior. A API principal não foi reiniciada contra dados reais.
- Preços dependem do catálogo armazenado; Pichau continua com a limitação já
  documentada de coleta direta bloqueada. Não há matching por SKU/frete por CEP.
- DLQ sem tela administrativa de replay; inspeção pelo painel RabbitMQ e registros.
- Broker de nó único, sem garantia contra perda física do host/disco. O teste
  reiniciou os serviços; não provocou queda de energia ou corrupção de armazenamento.
- Filas e fixtures de teste são preservadas e podem acumular. Limpeza futura exige
  avaliação/autorização; não foi realizada nesta entrega.

Ponto de retomada: entrega validada, documentação atualizada, alterações disponíveis
para revisão e nenhuma tarefa automática do agente pendente.





