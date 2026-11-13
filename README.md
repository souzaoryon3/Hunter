# Hunter

Sistema FastAPI/PostgreSQL com frontend HTML/CSS/JavaScript, autenticacao JWT,
busca de ofertas, historico, alertas assincronos RabbitMQ e Data Mining exploratorio.

## Aplicativo mobile

O cliente nativo Android/iOS fica em [`mobile/`](mobile/README.md), com React Native,
Expo e TypeScript. Usa a mesma API e o mesmo PostgreSQL da aplicação web.
Na pasta `mobile`, execute `npm ci` e `npm start`; o guia explica a conexão por
emulador, Wi-Fi ou USB e os testes. A branch de desenvolvimento é
`feat/app-mobile-react-native`, baseada em `feat/coleta-multiloja-scrapling-stealth`.

## Instalar em outro computador (Windows e Linux)

Requisitos: Git, Python **3.12**, Docker Engine/Desktop com containers Linux e
Docker Compose **2.24 ou superior** (BuildKit e additional_contexts). No Windows
10/11, habilite WSL2 e virtualizacao e inicie Docker Desktop; no Linux, instale
Engine e o plugin Compose e permita ao seu usuario acessar o daemon. Reserve
aproximadamente 8 GB de RAM e 10 GB de disco para imagens e testes de navegador.
Internet e necessaria no primeiro build para baixar imagens, pacotes e Chromium.
Nao e preciso instalar PostgreSQL, RabbitMQ, Node ou certificados no host para
usar o caminho Docker. Python usa apenas biblioteca padrao no comando de inicio.

Depois de a equipe autorizar e disponibilizar um **novo repositorio sem o historico
antigo**, clone sua URL (substitua o marcador; nenhum repositorio foi criado):

```text
git clone <URL_DO_NOVO_REPOSITORIO_DA_EQUIPE> Hunter
cd Hunter
python scripts/dev.py configure
python scripts/dev.py up
python scripts/smoke_dev.py
```

No Windows, use `py -3.12` se `python` nao apontar para Python 3.12. No Linux,
use `python3.12`. Os mesmos argumentos funcionam nos dois sistemas. Antes de
existir uma URL, extraia o snapshot preparado e execute os mesmos comandos dentro
da pasta `Hunter`. Nao copie `.git`, `.env.*`, `.secrets` ou dados do operador.

`configure` cria **.env.dev.local** ignorado, com tres segredos aleatorios novos;
recusa substituir um arquivo existente. Nao use os placeholders de `.env.example`
como senhas. A API nao carrega `.env` automaticamente; o helper passa esse arquivo
exclusivamente ao Compose de desenvolvimento e ignora overrides do terminal.

A stack `hunter-dev` cria rede e volumes proprios, inicializa um **banco vazio**,
aplica baseline/001 e migra??es 002?006, depois inicia API, worker, scheduler e
frontend. O bootstrap confere checksums a cada inicio, sem apagar dados e sem
recriar tabelas existentes. Uma oferta `DEMO FICTICIO - Teclado Hunter`, R$99,90,
com link example.invalid, permite testar busca e alertas. Nenhum usuario e
pre-cadastrado. Cadastre sua conta na tela. O dashboard tem modo demo separado,
em memoria; dados ficticios nunca sao rotulados como observacoes reais.

- Frontend: http://localhost:8088/index.html
- API/OpenAPI pelo proxy: http://localhost:8088/docs
- Readiness: http://localhost:8088/health/ready
- RabbitMQ Management: http://localhost:15688 (usuario `hunter_dev`; senha no
  campo DEV_RABBIT_PASSWORD do seu arquivo local; nao a envie em mensagens).

Somente frontend e Management publicam portas em **loopback**. PostgreSQL, AMQP
e API usam a rede interna; nao dependem de portas ou instalacoes do computador do
operador. Para alterar portas, edite DEV_HTTP_PORT/DEV_MANAGEMENT_PORT em seu
arquivo local e execute `up` novamente. Nao exponha esta stack HTTP fora do host:
o usuario PostgreSQL de desenvolvimento e administrativo dentro do seu volume.

```text
python scripts/dev.py status
python scripts/dev.py stop
python scripts/dev.py up
```

`stop` preserva containers e volumes. `up` reconstr?i o codigo e retoma os dados.
**Nao use down -v, prune, DROP ou TRUNCATE.** Nao combine compose.dev.yaml com
compose.yaml, compose.app.yaml ou compose.simulation.yaml.

## Testes reproduziveis

A suite completa possui um ambiente independente `hunter-team-test`, sem portas
publicadas, com banco/broker e credenciais novos. Nao usa o PostgreSQL principal,
os testes antigos do operador, DPAPI nem certificados locais:

```text
python scripts/dev.py test-configure
python scripts/dev.py test
python scripts/dev.py test-stop
```

O primeiro comando gera `.env.team-test.local`, sem substituir credenciais. O
segundo instala requirements-dev e Chromium no Linux, inicializa o esquema e
executa Ruff, unittest/integracao, cobertura minima de 80%, demo com dois workers,
ACK/retry/DLQ/idempotencia e navegador desktop/mobile com dashboard. Falhas retornam
codigo diferente de zero. Fixtures permanecem apenas no volume de testes. A rede
compartilhada de testes permite os destinos localhost:55432/5673 exigidos pelos
guards, sem abrir essas portas no host. Nunca altere guards para apontar ao principal.
`test-stop` preserva todos os dados. O runner encerrado tambem permanece para diagnostico.

Para checagem local opcional, crie venv com Python3.12 e instale:

```text
python -m venv .venv
# Windows: .venv\Scripts\activate ; Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m ruff check .
python scripts/check_quality.py
```

O ultimo comando requer Node.js no host para `node --check`. As suites de
integracao nativas exigem configuracao isolada conforme docs/FILA_RABBITMQ.md;
sem ela testes podem ser ignorados. O comando Docker acima e a validacao completa.
A CI e configuracao preparada; uma execucao remota so ocorrera apos publicacao autorizada.

## Banco e desenvolvimento

Nenhuma migracao e executada no startup da API. O servico `bootstrap` da stack dev
conclui o esquema antes dos processos runtime. Nao depende de dump, conta ou
credencial do banco principal. Para uma instalacao nativa **nova e vazia**, exporte
MIGRATION_DATABASE_URL e HUNTER_ENV=local no shell, depois
HUNTER_ALLOW_EMPTY_BOOTSTRAP=1 e `python -B -m ops.bootstrap`. Esse bootstrap recusa
banco com tabelas existentes. Confira sempre host, porta e nome antes de qualquer
operacao. Para evoluir um banco existente, use migracoes incrementais revisadas;
nao altere SQL ja aplicado. O executor atual aceita 002,003,004,005,006; uma nova versao
exige atualizar o executor e testes. Nao executar comandos administrativos do
operador para instalar o projeto da equipe.

- `backend/`: rotas, schemas, servicos, repositories, dependencias e seguranca.
- `frontend/`: paginas e assets, JavaScript de paginas em assets/js/pages.
- `config/`: validacao central de ambiente; nenhum fallback com senha.
- `messaging/`: outbox/publisher, worker, scheduler e idempotencia.
- `catalog_expansion/` e `scraping/`: fontes, parsers, quotas e coleta permitida.
- `data_mining/`: Pandas/K-Means; fontes reais e demo separadas.
- `ops/`, `migrations/`, `tests/`, `scripts/`: infraestrutura, esquema e validacao.

`app.py`/`auth.py` preservam compatibilidade com imports anteriores. O frontend e
servido na raiz HTTP mesmo estando organizado em frontend/. Para alterar codigo,
edite a camada correspondente, acrescente testes relevantes e execute `up` para
reconstruir imagens; nao ha bind mount/reload automatico. Consulte
[CONTRIBUTING.md](CONTRIBUTING.md), [arquitetura](docs/ARQUITETURA.md) e
[Data Mining](docs/DATA_MINING.md). Dependencias Python diretas estao fixadas em
requirements.txt; nao atualizar vers?es sem repetir a regressao. Tags Docker ainda
recebem patches: builds futuros nao sao garantia de identidade binaria.

## Desenvolvimento e simulacao de producao

A stack da equipe e HTTP local, sem certificados, sem copia de dados e com coleta
externa **desligada**. A simulacao anterior em compose.simulation.yaml exercita
TLS verify-full/AMQPS, HTTPS e privilegios minimos; seus scripts usam cofres DPAPI
especificos do operador Windows. Ela e opcional e nao faz parte da instalacao da
equipe. Nao compartilhe esses cofres nem copie os certificados para reproduzir o
ambiente dev. Em producao gere novos certificados e segredos no ambiente de destino,
separe runtime/migracao e configure rede privada, backups e observabilidade.
Consulte [simulacao](docs/SIMULACAO_PRODUCAO.md) e
[seguranca](docs/SEGURANCA_CONFIGURACAO.md). Nenhum deploy foi realizado.

## Problemas comuns

- Docker indisponivel: inicie Docker Desktop/Engine e confirme `docker version`.
- Compose sem additional_contexts/--wait: atualize o plugin para a versao requerida.
- Porta ocupada: altere somente DEV_HTTP_PORT/DEV_MANAGEMENT_PORT; nao encerre
  processos de outro projeto. Os testes nao publicam portas.
- Configure ja existe: reutilize seu arquivo local. Nao gere senhas novas para
  volumes existentes: PostgreSQL/RabbitMQ mantem as credenciais provisionadas.
- Bootstrap falhou: consulte logs locais do servico bootstrap, confirme destino e
  checksum. Nao apague volumes nem altere SQL aplicado para tentar corrigir.
- Login apos renovar JWT: autentique novamente. Nunca compartilhe tokens.
- Busca vazia: use `DEMO FICTICIO`; precos reais nao sao importados automaticamente.
- Dashboard sem dados reais: selecione origem demo; insuficiencia real e esperada.
- Diagnostico: use status e logs locais com cuidado; nao envie `compose config`,
  `docker inspect` ou ambientes completos, pois podem mostrar segredos.
- Navegador Linux: use o runner Bookworm preparado; ele instala Chromium e suas
  bibliotecas sem depender de Edge/Chrome do host.

## Transferir os dados atuais

O catalogo principal mais recente registrado tem 56 produtos e 63 observacoes.
Esses dados nao integram o snapshot de codigo. Em 08/11/2026 foi atualizado o
pacote de transferencia separado: 56 produtos, 63 observacoes, 56 candidatos,
6 alertas e 5 notificacoes, alem das tabelas legadas. A copia foi restaurada e
anonimizada em ambiente isolado, com contagens e hashes preservados.
Uma instalacao nova continua reproduzivel com esquema e demonstracao ficticia.
O coletor oficial Mercado Livre esta preparado, mas depende de aplicativo,
OAuth e permissoes efetivas; consulte [API Mercado Livre](docs/MERCADOLIVRE_API.md).

Para continuar com produtos reais, historico, candidatos, alertas e notificacoes,
use o pacote PostgreSQL criptografado **separado do Git**. O procedimento preserva
IDs/relacionamentos e anonimiza usuarios, feedback e auditoria somente na copia.
Nao sao necessarios segredos do operador. Siga o
[guia de transferencia Windows/VS Code/Docker](docs/TRANSFERENCIA_WINDOWS.md)
**antes de iniciar a stack de destino**: o restore exige banco novo e vazio.
Use uma instancia nomeada com portas proprias, por exemplo `--instance equipe`.

## Compartilhamento seguro

O historico Git original contem segredos antigos e **nao deve ser publicado**.
A preparacao gera snapshot sem .git, com manifesto SHA256, preservando o original.
Leia [estrategia e inventario](docs/COMPARTILHAMENTO.md). Segredos locais, backups,
dados de usuarios e volumes nao fazem parte do pacote. Nao execute git add . no
repositorio antigo como estrategia de saneamento: .gitignore nao limpa historico.
Nenhum commit, push, novo repositorio remoto ou deploy e criado automaticamente.

### Coleta de perifericos

`.venv\Scripts\python.exe -B scripts/collect_peripherals.py --target 50 --max-pages 5`

Busca ate 50 produtos unicos por loja em dez categorias, com cota inicial de cinco
por categoria e redistribuicao das vagas restantes. Segue links de proxima pagina
presentes no HTML: padrao de cinco paginas por categoria, configuravel de uma a dez.
O relatorio JSON com ofertas, categorias e resultados HTTP fica em `%TEMP%/HunterRuntime`.
Esta execucao nao grava no PostgreSQL.

A consulta ao `robots.txt` esta desativada por padrao nos coletores compartilhados
e em `collect_discovered.py`. Para reativa-la, defina `HUNTER_RESPECT_ROBOTS=1`.
CAPTCHA, autenticacao e respostas 401/403/429 continuam interrompendo a coleta.


O modo `--transport auto` usa navegador Scrapling/Patchright em Fast Shop, Amazon,
Magalu e GK, e HTTP nas demais lojas. `--transport http` e `--transport browser`
permitem selecionar explicitamente o transporte nesta coleta. Perfis de navegador
sao temporarios; a Amazon inicia pela homepage e conserva cookies na mesma coleta.
Paginas iguais entre categorias sao reutilizadas em memoria; HTTP 503 recebe uma
unica repeticao com espera limitada. CAPTCHA e autenticacao continuam interrompendo
a coleta. HTTP 423 com pagina de loja bloqueada e classificado como indisponibilidade
da loja e tambem suspende a fonte nos coletores periodicos.

Instalacao do navegador apos instalar `requirements.txt`:

```powershell
.venv\Scripts\python.exe -m patchright install chromium
.venv\Scripts\python.exe -m playwright install chromium
```

O segundo comando prepara os testes de interface existentes. Versoes utilizadas:
Scrapling 0.5.1, Playwright 1.65.1 e Patchright 1.64.4.
Para repetir somente as quatro lojas desta etapa, sem Mercado Livre:

```powershell
.venv\Scripts\python.exe -B scripts/collect_peripherals.py --store "Fast Shop" --store "Amazon Brasil" --store Magalu --store "GK InfoStore" --target 50 --max-pages 5
```
