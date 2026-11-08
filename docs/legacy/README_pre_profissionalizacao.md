# PI_fixed
hunter app

Dashboard analítico local: `http://127.0.0.1:5500/dashboard.html` (link **Análises**).
Estatísticas com Pandas, sinais de queda e K-Means com proteção contra amostra
insuficiente. Demonstração sintética separada do catálogo real. Métodos, endpoints
e testes em [docs/DATA_MINING.md](docs/DATA_MINING.md).

Coleta periódica limitada integrada ao scheduler existente: configuração, fontes
permitidas, cooldown e limites em [docs/COLETA_PERIODICA.md](docs/COLETA_PERIODICA.md).
Mercado Livre/Pichau permanecem desativados enquanto houver bloqueios de acesso.

## Executar localmente

Requer Python 3.12, PostgreSQL e o esquema existente do Hunter. Instale as
dependências com `python -m pip install -r requirements.txt` no ambiente virtual.
Configure `DATABASE_URL` se o banco não estiver no endereço local usado em `app.py`.
Nenhuma tabela é criada ou modificada automaticamente ao iniciar a API.

Configure o segredo JWT conforme abaixo e inicie a API na porta 8000. Em outro
terminal, inicie o frontend:

```powershell
.\.venv\Scripts\python.exe -B serve_frontend.py
```

Abra `http://127.0.0.1:5500/index.html`. A API fica em
`http://127.0.0.1:8000/docs`. O frontend local usa a porta 8000 no mesmo hostname.
Em hospedagem, ele usa a mesma origem do site; encaminhe as rotas da API ao backend
ou configure `window.HUNTER_API_URL` antes de carregar `ui.js`.
`CORS_ORIGINS` aceita origens separadas por vírgula; por padrão permite somente
`http://127.0.0.1:5500` e `http://localhost:5500`.

Use sempre esse endereço para visualizar o projeto. O servidor local serve o
diretório do próprio projeto e desabilita cache de HTML, CSS e JavaScript para
evitar que versões anteriores reapareçam durante o desenvolvimento. CSS e
JavaScript também têm versão explícita nos links das páginas. O servidor não
disponibiliza arquivos Python, configuração do Git ou listagens de diretórios.

## Funcionalidades

- Busca pública paginada (24 ofertas por página), filtro de loja e faixa de preço.
- Filtros preservados na URL, links seguros e criação de alerta pela oferta.
- Cadastro e login, expiração de sessão e retorno à página desejada após login.
- Perfil preenchido automaticamente; alterações de e-mail/senha exigem senha atual.
- Alertas com criação, edição, exclusão e comparação com o menor preço no catálogo.
- Feedback com mensagem única, histórico pessoal, edição e exclusão.
- Interface compartilhada em `ui.css` e `ui.js`, acessível e adaptada ao celular.

O catálogo antigo de KaBuM!/Mercado Livre não registra frete nem data da coleta.
Pichau registra preço Pix/cartão, condições de frete e data/fonte de captura.
A interface não presume frete grátis nem atualização em tempo real. A página de
alertas mantém a comparação imediata e agora consulta notificações persistidas,
geradas por agendador e worker independentes com RabbitMQ. Não há envio de e-mails.
Nenhum scraper é executado pela busca ou pelo gerenciamento de alertas.

## Sprint SCRUM-28 a SCRUM-33 — alertas assíncronos

Instalação, migração incremental, RabbitMQ por Docker Compose, API, worker,
agendador, testes isolados e roteiro de demonstração com falha simulada estão em
[docs/FILA_RABBITMQ.md](docs/FILA_RABBITMQ.md). O banco existente é preservado;
os testes utilizam outro PostgreSQL na porta 55432 e outro broker na porta 5673.

Os tokens novos identificam a conta pelo ID. Tokens antigos baseados em e-mail
exigem novo login após esta atualização. A validade padrão continua em 60 minutos.

## Testes

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Para incluir os testes de integração, configure `HUNTER_TEST_DATABASE_URL` com a
conexão de um banco de testes com o esquema do Hunter. Eles criam registros
temporários dentro de transações revertidas ao final, incluindo registros de
auditoria gerados pelo banco. Sequências de IDs podem avançar mesmo após rollback.

Com o frontend local ativo, execute os testes de navegador usando Playwright
(já incluído nas dependências) e o Microsoft Edge instalado:

```powershell
.\.venv\Scripts\python.exe -B tests/browser_ux.py
```

Os testes de navegador simulam a API e não gravam no banco real.

## Segredo JWT

Antes de iniciar a API, configure `JWT_SECRET_KEY` com um segredo aleatório.
A aplicação não inicia se a variável estiver ausente, vazia ou contiver apenas espaços.

No PowerShell, a partir do diretório do projeto:

```powershell
$env:JWT_SECRET_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

A variável fica disponível na sessão atual do terminal. Para persistir o mesmo
segredo no ambiente do seu usuário do Windows:

```powershell
[Environment]::SetEnvironmentVariable("JWT_SECRET_KEY", $env:JWT_SECRET_KEY, "User")
```

Novos terminais recebem a variável persistida. Reinicie a API depois de configurar
ou trocar o segredo. Mantenha o mesmo valor entre reinicializações e instâncias;
trocar o segredo invalida os tokens emitidos anteriormente. Os tokens continuam
expirando após 60 minutos por padrão.

Não coloque o segredo no código, em commits ou em mensagens. Arquivos `.env`
não são carregados automaticamente pela aplicação.

## Catálogo Pichau

O scraper `scraping/buscar_produtospichau.py` não roda ao importar nem é executado
pela API. Configure `DATABASE_URL` no terminal com a conexão PostgreSQL do Hunter.
Não há senha embutida nesse scraper. Antes de usar a API atualizada, crie a tabela
Pichau executando a migração `migrations/001_produtos_pichau.sql` ou uma primeira
carga com `--init-db`. As tabelas das outras lojas não são alteradas.

```powershell
$env:DATABASE_URL = 'postgresql://USER:REPLACE_PASSWORD@DB_HOST:5432/DB_NAME'
.\.venv\Scripts\python.exe -B scraping/buscar_produtospichau.py --dry-run
.\.venv\Scripts\python.exe -B scraping/buscar_produtospichau.py --init-db
```

Use `--url https://www.pichau.com.br/perifericos/mouse` para outra categoria pública.
Cada execução aceita até quatro páginas, respeita robots.txt, aguarda entre
requisições e não consulta APIs privadas, checkout ou paginação com parâmetros.
O parser exige preço Pix reconhecível e distingue preço à vista, cartão e parcela.
Se o markup mudar, a coleta falha sem gravar dados incertos.

O acesso direto retornou HTTP 403 durante a implementação. O script interrompe
a carga em bloqueios, manutenção ou ausência de produtos, sem apagar ofertas.
Não utiliza proxies, disfarces ou resolução de desafios. A coleta direta permanece
dependente da liberação de acesso pela loja; não há atualização agendada.

A carga inicial contém seis produtos reais consultados no conteúdo público da
categoria de teclados por uma ferramenta de navegação, que pode fornecer conteúdo
em cache. `capturado_em` é a data da consulta, não a atualização do preço na loja.
A origem `captura_publica` aparece na interface. Para importar essa captura:

```powershell
.\.venv\Scripts\python.exe -B scraping/buscar_produtospichau.py --snapshot scraping/dados/pichau_captura_inicial.json --init-db
```

Também é possível importar HTML público salvo com `--html CAMINHO --url URL_ORIGINAL`.
As cargas são transacionais e atualizam por URL, sem duplicar nem substituir uma
captura mais recente por uma antiga. Nenhuma oferta ausente numa carga é apagada.
Estoque de ofertas antigas deve ser confirmado na loja. Valores desconhecidos de
frete permanecem `null`; frete regional não entra no filtro universal. Preço total
com frete ainda depende de consulta por CEP, que esta integração não faz.
