# Sprint Hunter — SCRUM-28 a SCRUM-33

## O que foi implementado

| História | Implementação |
|---|---|
| SCRUM-28 | `messaging.service.scan`: reutiliza o catálogo da API, compara menor preço com alvo e detecta a transição para atingido. |
| SCRUM-29 | Outbox PostgreSQL, mensagens persistentes, filas duráveis quorum, publicação mandatory e publisher confirms. |
| SCRUM-30 | Processo independente `python -m messaging.worker`, prefetch 10 e ACK manual após persistência. |
| SCRUM-31 | Agendador independente, worker assíncrono e notificações persistidas, sem executar scrapers ou bloquear requisições da API. |
| SCRUM-32 | Eventos e logs com status, tentativas, horários, falhas de publicação/consumo/DLQ e códigos de erro sem segredos. |
| SCRUM-33 | Retentativas limitadas, espera progressiva, recuperação da outbox, DLQ confirmada, quarentena de mensagens inválidas e idempotência. |

Fluxo: catálogo armazenado → detecção/agendador → outbox PostgreSQL → RabbitMQ →
worker → notificação PostgreSQL → página Meus alertas.

## Semântica e garantias

- A primeira detecção de preço menor ou igual ao alvo cria um evento. Novas
  varreduras na mesma condição não repetem o aviso. Se o preço ficar acima e
  depois voltar a atingir o alvo, um novo evento é criado. Alterar produto/alvo
  reavalia a condição. O critério de correspondência continua sendo o termo de
  busca contido no nome, igual ao sistema anterior; não identifica SKU equivalente.
- A detecção e a outbox são gravadas numa transação. Sem RabbitMQ, o evento fica
  pendente e é retomado. A API continua funcionando sem conexão com o broker.
- O publisher só marca a publicação após confirmação. Se cair entre a publicação
  e o commit, pode repetir a mensagem: a entrega é **pelo menos uma vez**, não
  exatamente uma vez. `event_id` único na notificação e locks impedem duplicação
  do efeito. Publicações sem processamento são reenviadas após a janela de recuperação.
- Worker persiste notificação e resultado na mesma transação. Só depois envia ACK.
  Falha de banco/conexão não recebe ACK; a entrega é reenfileirada ou retomada ao
  reconectar. Uma entrega duplicada de evento finalizado só é confirmada.
- Falhas de processamento são registradas e passam para `retry`. O worker pode
  dar ACK porque o trabalho está preservado no banco. O agendador republica após
  a espera: a primeira espera é 30s, depois 60s (configuração padrão).
- Após três tentativas, o evento passa a `dead_pending`. O agendador publica na
  DLQ com confirmação e só então marca `dead`. Se falhar, a intenção permanece
  no banco. Não há reprocessamento automático infinito de falhas de negócio.
- Filas quorum também têm roteamento de dead-letter configurado para rejeições
  do broker. A transferência explícita feita pela aplicação usa publisher confirms;
  o roteamento interno do broker não substitui a outbox. Eventos publicados sem
  resultado continuam recuperáveis mesmo se o limite de redelivery do broker agir.
- Mensagens inválidas/desconhecidas são registradas por hash, copiadas à DLQ
  de forma confirmada e depois recebem ACK. O corpo não é registrado no banco.
- Alertas excluídos ou com produto/alvo diferente do evento são cancelados antes
  de notificar. Avisos já persistidos continuam consultáveis após excluir o alerta.
  A exclusão da conta mantém a política existente de remoção de dados daquele usuário.

## Instalação no ambiente existente (sem trocar o PostgreSQL)

Requisitos: Python 3.12, Docker Desktop em modo Linux e esquema atual do Hunter
com a migração Pichau já aplicada. Na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
. .\scripts\queue_environment.ps1
docker compose up -d --wait rabbitmq
```

O script gera credenciais aleatórias em `.env.queue.local`, ignorado pelo Git e
pelo Docker build. Carregue-o em cada terminal. Não publique esse arquivo. O
Compose mantém o RabbitMQ em volume próprio e **não cria nem modifica seu banco
real**. Portas 5672/15672 ficam restritas a localhost. Não use `docker compose
config` em relatórios: a saída pode conter segredos resolvidos.

Configure `DATABASE_URL` no ambiente com a conexão existente e `JWT_SECRET_KEY`
conforme o README. Não copie credenciais para arquivos versionados. Os processos
não carregam `.env` automaticamente; o script configura as variáveis desta sessão.

Aplique explicitamente a migração incremental antes de usar notificações:

```powershell
.\.venv\Scripts\python.exe -B -m messaging.migrate
```

A migração 002 cria somente tabelas/índices novos e o registro de migração, em
transação, com trava e checksum. Não remove tabelas/produtos nem altera as tabelas
antigas. Não é aplicada automaticamente no startup da API. Faça o backup
operacional habitual antes de aplicar migrações em ambiente de produção.

Em terminais separados, com as mesmas variáveis:

```powershell
# API
.\.venv\Scripts\python.exe -B -m uvicorn app:app --host 127.0.0.1 --port 8000
# Worker
.\.venv\Scripts\python.exe -B -m messaging.worker
# Agendador
.\.venv\Scripts\python.exe -B -m messaging.scheduler
# Frontend
.\.venv\Scripts\python.exe -B serve_frontend.py
```

Abra `http://127.0.0.1:5500/alertas.html`. A página mostra notificações, contador
de não lidas, paginação, atualização manual e consulta automática a cada 30s
enquanto visível na primeira página. Não há e-mail ou push do navegador.

Endpoints autenticados: `GET /notificacoes?pagina=1&limite=20` e
`PUT /notificacoes/{id}/lida`. Cada usuário acessa somente os próprios avisos.
Marcar como lida repetidamente mantém o horário original.

Configurações opcionais, somente no ambiente:

| Variável | Padrão | Uso |
|---|---|---|
| HUNTER_SCAN_SECONDS | 60 | Intervalo dos ciclos de detecção e publicação |
| HUNTER_MAX_ATTEMPTS | 3 | Tentativas de processamento por evento |
| HUNTER_RETRY_SECONDS | 30 | Base da espera progressiva, até 32 vezes a base |
| HUNTER_RECOVERY_SECONDS | 300 | Republicar evento publicado sem resultado |
| HUNTER_QUEUE_PREFIX | hunter | Prefixo das filas `.price` e `.price.dead` |

O tempo efetivo da retentativa inclui o próximo ciclo do agendador. Mantenha a
janela de recuperação maior que a duração normal do processamento. A publicação
pode tentar indefinidamente recuperar indisponibilidade de infraestrutura, com
intervalo e registro; o limite de três se refere ao processamento do evento.

## Testes isolados

```powershell
. .\scripts\queue_environment.ps1 -Test
docker compose --profile test up -d --wait postgres-test rabbitmq-test
.\scripts\test_queue.ps1
```

O banco exclusivo é `hunter_test` em 55432, e o broker usa vhost `hunter_test`
na porta 5673. O bootstrap e a demonstração recusam conexões fora desse ambiente.
O esquema mínimo criado é uma fixture para testes, não uma migração do banco real.
Os testes existentes de API/Pichau rodam também nesse banco. Os testes da fila
usam transações revertidas e filas aleatórias. IDs podem avançar no banco de teste.
As filas temporárias são preservadas, sem purge ou exclusão. Fixtures de navegador
e demonstração permanecem somente no banco isolado; nenhum volume é removido.
O teste de navegador inicia API 8001, frontend 5501, agendador e worker, usa
dados sintéticos persistentes somente no banco isolado, e encerra esses processos
ao finalizar. Requer Microsoft Edge instalado e portas 8001/5501 livres.
O roteiro automatizado inclui `tests/demo_queue.py`, que inicia dois workers,
publica duplicatas e valida falha até a DLQ. Ele mantém fixtures sintéticas apenas
no banco isolado e permite repetir a demonstração sem apagar dados.

Para containers que já existem, preserve-os usando:

```powershell
. .\scripts\queue_environment.ps1 -Test
docker compose --profile test start postgres-test rabbitmq-test
```

Não use `start --wait`: a versão do Compose validada não aceita essa opção.
Aguarde os healthchecks saudáveis antes dos testes. O comando `up` da instalação
inicial não foi usado para recriar recursos nesta recuperação.

### Recuperação após reinício real

Com o ambiente isolado ativo, sem outros testes, workers ou agendadores em execução:

```powershell
. .\scripts\queue_environment.ps1 -Test
.\.venv\Scripts\python.exe -B tests/restart_queue.py prepare
docker compose --profile test restart postgres-test rabbitmq-test
# Aguarde ambos os healthchecks saudáveis, mantendo os volumes existentes.
.\.venv\Scripts\python.exe -B tests/restart_queue.py verify
```

`prepare` adiciona quatro fixtures: duas mensagens já publicadas (uma entrega sem
ACK, devolvida à fila ao fechar o canal), um evento em retry e um pendente na
outbox. A referência fica em `.hunter-recovery.local.json`, ignorado pelo Git e
pelo Docker build. `verify` consome as mensagens existentes antes de republicar
qualquer evento, recupera retry/outbox e verifica quatro notificações únicas,
mesmo com entrega duplicada. Não é uma simulação de corte de energia durante fsync:
valida reinício dos serviços, persistência e recuperação lógica de entregas.

Resultado de 24/10/2026: suíte de 26 testes, demonstração com dois workers,
validação completa com navegador e teste de reinício aprovados. Relatório em
[RELATORIO_SCRUM_28_33.md](RELATORIO_SCRUM_28_33.md).

## Demonstração para o professor

Use **somente o ambiente isolado**. Não mantenha outro worker/agendador desse
ambiente aberto com configurações diferentes durante a demonstração.

1. Execute os dois primeiros comandos da seção de testes, depois:

   ```powershell
   .\.venv\Scripts\python.exe -B -m messaging.testing
   .\.venv\Scripts\python.exe -B -m messaging.demo seed
   ```

   Isso cria usuário, produto fictício com preço 90 e alerta alvo 100. O login fica
   apenas no arquivo local ignorado `.hunter-demo.local.json`; consulte-o no seu
   computador, sem incluí-lo em slides, commits ou relatórios. Todas essas ações
   são limitadas ao banco de teste. A data/fonte dos produtos reais não é alterada.

2. Abra quatro terminais na raiz, carregue `. .\scripts\queue_environment.ps1 -Test`
   em cada um e inicie API porta 8000, frontend porta 5500, worker e agendador usando
   os comandos da instalação. Pare antes servidores locais dessas portas, se houver.
   Para demonstrar falhas, inicie o worker assim:

   ```powershell
   .\.venv\Scripts\python.exe -B -m messaging.worker --demo-failures
   ```

   Esse modo é recusado fora do ambiente isolado. Ele falha somente nos eventos
   explicitamente marcados pela fixture; não altera o comportamento normal.

3. Faça login em `http://127.0.0.1:5500/login.html`, abra Meus alertas e atualize as
   notificações. Veja a oferta de 90 para alvo 100. Confira os registros:

   ```powershell
   .\.venv\Scripts\python.exe -B -m messaging.demo status
   ```

4. Demonstre idempotência:

   ```powershell
   .\.venv\Scripts\python.exe -B -m messaging.demo duplicate
   ```

   O mesmo evento entra duas vezes na fila. Após o consumo, a notificação continua
   única. Marque-a como lida e recarregue a página para mostrar persistência.

5. Demonstre falha simulada:

   ```powershell
   .\.venv\Scripts\python.exe -B -m messaging.demo failure
   ```

   Com worker `--demo-failures` e agendador ativos, observe `attempts` chegar a 3,
   logs de `retry`, `dead_pending` e publicação `dead_letter` confirmada. Depois:

   ```powershell
   .\.venv\Scripts\python.exe -B -m messaging.demo status
   ```

   O evento termina em `dead`, sem criar notificação falsa. O painel RabbitMQ de
   teste fica em `http://127.0.0.1:15673`; use as credenciais do arquivo local,
   vhost `hunter_test` e fila `hunter_test.price.dead`. Apenas consulte a fila;
   não use purge ou remoção de volumes. Com intervalos de teste, leva alguns ciclos.

6. Para mostrar publicação recuperável, pare apenas o worker, crie um novo alerta
   pelo frontend e observe mensagens aguardando. Reinicie o worker e veja o aviso.
   A indisponibilidade do publisher é coberta também pelo teste automatizado que
   mantém a outbox pendente e a publica novamente quando o broker retorna.

Para encerrar os processos Python use Ctrl+C. Para parar os containers sem remover
dados, `docker compose --profile test stop postgres-test rabbitmq-test`. Não rode
`down -v`, purge ou comandos de limpeza sem avaliar e autorizar a remoção de dados.

## Limitações reais

- Nenhum scraper é executado e nenhum preço é atualizado por esta Sprint. Alertas
  refletem o catálogo armazenado, inclusive a captura pública antiga da Pichau.
- Sem frete por CEP, identificação por SKU, e-mail, push ou histórico de preços.
- Uma instância RabbitMQ com volume não fornece alta disponibilidade contra perda
  do host/disco. Para produção, são necessários backup, TLS, permissões por vhost,
  monitoramento, retenção dos logs e avaliação de cluster.
- Eventos em `dead` exigem inspeção operacional. Não existe botão de replay
  administrativo nesta entrega. A DLQ e o log permitem investigar a causa.
- A varredura serial usa a regra atual e bloqueia brevemente os alertas enquanto
  calcula as ofertas. Para grande volume, medir e otimizar lotes/índices.
- A migração foi validada em PostgreSQL isolado; a aplicação no banco real é uma
  etapa explícita de implantação, não realizada pelos testes.

Referências: [confirmações e ACKs](https://www.rabbitmq.com/docs/confirms),
[cliente aio-pika](https://docs.aio-pika.com/apidoc.html).
