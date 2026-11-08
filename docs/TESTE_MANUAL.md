# Hunter — roteiro manual da Sprint SCRUM-28 a SCRUM-33

Use somente o ambiente isolado já validado. Não execute migrações ou scrapers.
Os dados reais não serão usados. Execute os comandos PowerShell na raiz PI_Hunter.

## 1. Docker e containers existentes

Abra Docker Desktop pelo menu Iniciar e aguarde o engine ficar disponível. Se
preferir iniciar pelo PowerShell:

```powershell
Start-Process -FilePath 'C:\Program Files\Docker\Docker\Docker Desktop.exe' -WindowStyle Hidden
```

Depois:

```powershell
. .\scripts\queue_environment.ps1 -Test
docker compose --profile test start postgres-test rabbitmq-test
docker ps --format '{{.Names}} | {{.Status}}'
```

Aguarde os dois containers ficarem saudáveis (`healthy`). Esse comando usa os
containers e volumes existentes; não use `down -v`, purge ou recriação de banco.
O banco de teste está em 55432; RabbitMQ de teste em 5673/15673.

## 2. Quatro terminais para a aplicação

Abra quatro terminais na raiz. Em TODOS execute primeiro:

```powershell
. .\scripts\queue_environment.ps1 -Test
```

Isso configura a conexão exclusiva de teste e o mesmo segredo JWT local, sem
exibir valores. Não remova `-Test` durante esta demonstração.

**Terminal 1 — API:**

```powershell
.\.venv\Scripts\python.exe -B -m uvicorn app:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend:**

```powershell
.\.venv\Scripts\python.exe -B serve_frontend.py
```

**Terminal 3 — worker:**

```powershell
.\.venv\Scripts\python.exe -B -m messaging.worker --demo-failures
```

**Terminal 4 — agendador:**

```powershell
.\.venv\Scripts\python.exe -B -m messaging.scheduler
```

`--demo-failures` funciona apenas no ambiente isolado e afeta somente eventos
marcados pela demonstração de falha. Eventos normais continuam sendo processados.
Para mostrar dois workers, abra um quinto terminal, carregue o ambiente de teste
e execute o mesmo comando do worker. Não suba outra API/frontend nas mesmas portas.

Se a porta 8000/5500 já estiver ocupada, identifique o servidor antes de iniciar
outro: não use uma cópia diferente do Hunter. API: `http://127.0.0.1:8000/docs`.

## 3. Login e oferta de demonstração

Abra `http://127.0.0.1:5500/login.html`. O usuário sintético já foi criado nos
testes. Consulte email/senha apenas no seu computador abrindo
`.hunter-demo.local.json` num editor. Não publique o arquivo nem mostre a senha
em slides ou relatórios. Para o painel RabbitMQ, as credenciais locais ficam em
`.env.queue.local` (campos HUNTER_RABBIT_USER e HUNTER_RABBIT_PASSWORD).

Esses dois arquivos são ignorados pelo Git. Caso estejam ausentes, não recrie
bancos/volumes: retome a configuração conforme a documentação técnica.

Na busca do Hunter, procure `HunterDemo`, selecione uma oferta sintética de
R$ 90,00 e copie o nome completo. Nenhum scraper é executado pela busca.

## 4. Identificação, publicação, consumo e notificação — SCRUM-28 a SCRUM-31

1. Em Meus alertas, crie um NOVO alerta para o nome copiado, com alvo R$ 100,00.
2. Aguarde alguns segundos para o agendador verificar e o worker consumir.
3. Clique em Atualizar notificações. Deve aparecer a oferta de R$ 90,00.
4. Marque como lida e recarregue a página: o estado deve permanecer.
5. Edite/exclua um alerta sintético para conferir o CRUD existente.

Um alvo abaixo do preço atual não deve gerar uma nova notificação. Avisos antigos
continuam no histórico: identifique o novo alerta/produto que acabou de criar.

## 5. Painel RabbitMQ e mensagens aguardando

Abra `http://127.0.0.1:15673`, autentique-se com as credenciais locais e selecione
o vhost `hunter_test`. Em Queues and Streams, procure:

- `hunter_test.price`: fila principal.
- `hunter_test.price.dead`: dead-letter queue.

`Ready` indica mensagens aguardando entrega; `Unacked` indica entregues sem ACK.
Com workers ativos, mensagens podem desaparecer rapidamente da principal porque
foram processadas, enquanto a notificação fica persistida no PostgreSQL.

Para observar a fila: pare TODOS os workers com Ctrl+C, mantenha o agendador ativo
e crie outro alerta sintético atingido. Veja `Ready` aumentar. Reinicie os workers:
a fila deve esvaziar e a notificação aparecer no Hunter. Não use Purge/Delete.
Se inspecionar o corpo por Get messages, mantenha a opção de reenfileirar habilitada
para não remover mensagens durante a inspeção.

## 6. Logs e idempotência — SCRUM-32

Em outro terminal com o ambiente de teste carregado:

```powershell
.\.venv\Scripts\python.exe -B -m messaging.demo status
.\.venv\Scripts\python.exe -B -m messaging.demo duplicate
```

A duplicação usa o evento original da fixture de demonstração; a notificação
original deve continuar única. Execute `status` novamente para ver registros
`duplicate`, fases, horários, status e tentativas. Esses comandos mostram apenas
o usuário da fixture, não todos os alertas criados manualmente pelo navegador.

O histórico preserva execuções anteriores, inclusive registros antigos anteriores
à correção do relógio. Avalie os registros mais recentes da demonstração atual.

## 7. Falha, retry e DLQ — SCRUM-33

Com agendador e worker(s) `--demo-failures` ativos:

```powershell
.\.venv\Scripts\python.exe -B -m messaging.demo failure
```

Aguarde alguns ciclos e consulte:

```powershell
.\.venv\Scripts\python.exe -B -m messaging.demo status
```

O novo evento deve registrar três tentativas e terminar em `dead`, com logs
`retry`, `dead_pending` e confirmação de publicação `dead_letter`. Não deve gerar
uma notificação de sucesso. No painel, a fila `hunter_test.price.dead` recebe a
mensagem. Eventos antigos na DLQ foram preservados; observe a contagem aumentar.

## 8. Encerrar sem apagar dados

Use Ctrl+C nos terminais Python. Se desejar parar também os serviços isolados:

```powershell
docker compose --profile test stop postgres-test rabbitmq-test
```

Não é necessário remover containers ou volumes. A recuperação após reinício já foi
validada; seu roteiro adicional está em `FILA_RABBITMQ.md`, sem necessidade de
reexecutar a suíte longa para esta conferência manual.
