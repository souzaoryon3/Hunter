# Hunter ? continuidade da equipe

Snapshot sem historico Git. Consulte README.md, CONTRIBUTING.md e docs/COMPARTILHAMENTO.md.
Banco novo via scripts/dev.py; nenhum usuario, cofre, backup ou segredo do operador foi copiado.
Nao publicar o historico do repositorio original. Nenhum commit/push foi criado por esta preparacao.

## 2026-11-12 - Transporte Scrapling stealth

- Ativados `impersonate='chrome'` e `stealthy_headers=True` no transporte existente; preservados TLS, limite de tentativa, redirects controlados e verificacao de robots/desafios.
- Teste do transporte atualizado para verificar Chrome e headers stealth.
- Validacao: 14 testes de coleta aprovados; teste real via proxy HTTP local retornou 200, confirmou encaminhamento e User-Agent Chrome.
- Suite coleta/catalogo/Pichau: 45 testes executados, 8 dependentes de ambiente ignorados, sem falhas na verificacao inicial; repetida apos ativacao.
- Limitacao: Scrapling oferece suporte a proxies, mas nenhum provedor/proxy externo foi configurado. Teste local nao comprova acesso a lojas nem IP de saida externo. Stealth ativado e HTTP, sem navegador StealthyFetcher.


## 2026-11-12 - Coleta multiloja e robots opcional

- Por instrucao explicita do operador, a consulta ao robots.txt esta desativada por padrao em public_sources e collect_discovered. HUNTER_RESPECT_ROBOTS=1 reativa o comportamento anterior. Mantidas verificacoes de dominio, TLS, autenticacao, CAPTCHA e interrupcao por erros de acesso.
- Novo coletor: scripts/collect_peripherals.py --target 50 --max-pages 5. Dez categorias, cotas iniciais, deduplicacao por URL, filtro pelo nome e redistribuicao equilibrada das vagas. De uma a dez paginas por categoria; padrao cinco. Usa apenas links de proxima pagina presentes no HTML.
- Corrigidos headers HTTP sem distincao de maiusculas/minusculas, redirects publicos KaBuM, desconto Pix Pichau dividido em spans e cartoes Terabyte com preco Pix separado de preco antigo/parcelas.
- Coleta real concluida: KaBuM 50 (5 em cada categoria), Pichau 50 (6 categorias disponiveis), TerabyteShop 50 (10 categorias). Total: 150 produtos unicos por identidade loja/URL, com precos e origem reais. JSON consolidado validado em local-reports/peripherals-20261112.json (ignorado pelo Git). Nenhuma gravacao no PostgreSQL.
- Metas pendentes: Mercado Livre redireciona para verificacao de conta; Magalu HTTP 403; GK InfoStore HTTP 423; Amazon sem ofertas reconhecidas e HTTP 503 em diagnostico posterior; Fast Shop entrega HTML sem ofertas/precos. StealthyFetcher nao inicia porque patchright nao esta instalado. Nao foram simulados produtos para completar metas.
- Testes: unittest discover -s tests -q: 173 executados, 107 aprovados e 66 ignorados por dependerem de integracao/ambiente. git diff --check sem erros. Aviso de depreciacao preexistente do lxml.
- Arquivos desta etapa: README.md; CONTINUIDADE.md; scraping/public_sources.py; scraping/transport.py; scraping/peripherals.py; scraping/tech_stores.py; scraping/buscar_produtospichau.py; scripts/collect_peripherals.py; scripts/collect_discovered.py; tests/test_collect_sample.py; tests/test_peripherals.py; tests/test_pichau.py.


## 2026-11-12 - Atualizacao Scrapling e correcoes sem Mercado Livre

- Autorizacao: usar versoes estaveis mais novas e corrigir Fast Shop, Amazon, Magalu e GK. Nenhum acesso novo ao Mercado Livre ou alteracao de seu coletor nesta etapa.
- Instalados e fixados Scrapling[fetchers] 0.5.1, Playwright 1.65.1, Patchright 1.64.4 e curl_cffi 0.17.0. Ajustadas somente as dependencias transitivas necessarias (anyio, certifi, cffi, click, pyee, typing_extensions). Navegadores Chromium instalados para Patchright e Playwright; pip check sem conflitos.
- BrowserSession com navegador headless em perfil temporario, verificacao das navegacoes publicas, erros de rede classificados, sem resolver desafios. Mantem sessao/cookies por loja e fecha ao terminar. Amazon visita a homepage antes da busca: isto resolveu o 503 observado no acesso direto na execucao validada.
- Coleta de perifericos seleciona navegador automaticamente somente nas quatro lojas pendentes. CLI --transport auto/http/browser. Reutiliza paginas identicas em memoria e repete HTTP 503 uma unica vez com espera limitada. HTTP 403, autenticacao e CAPTCHA continuam interrompendo.
- Fast Shop: parser para cartoes renderizados, nome em elementos aninhados, preco a vista explicitamente identificado; nao escolhe Prime, preco antigo ou parcelas. Corrigida paginacao que expunha /[...slug] em vez do caminho real da categoria.
- Amazon: parser por cartao/ASIN, preco atual unico, imagem da oferta e URL canonica derivada de links observados. Remove tracking e valida links patrocinados; rejeita preco ambiguo ou produto sem link correspondente.
- GK: HTTP 423 com pagina Loja bloqueada agora e loja_indisponivel; coletores periodicos tambem classificam a fonte como bloqueada, evitando insistir enquanto estiver indisponivel.
- Coleta real validada: Fast Shop 50 ofertas em 7 categorias; Amazon 50 ofertas, 5 em cada uma das 10 categorias. Relatorio novo: local-reports/peripherals-corrections-20261112.json (ignorado pelo Git), 100 ofertas adicionais nesta etapa, sem gravacao no PostgreSQL. O relatorio anterior de 150 ofertas foi preservado.
- Pendencias externas: Magalu continua HTTP 403 na homepage e nas buscas, tambem em navegador; GK mostra Loja bloqueada pelo provedor, inclusive na homepage. Nao foram simulados resultados nem ultrapassadas verificacoes de conta. Nenhum proxy externo configurado.
- Validacao final: unittest discover -s tests -q: 185 executados, 119 aprovados e 66 ignorados por integracao/ambiente; Ruff dos arquivos Python alterados aprovado; pip check aprovado; git diff --check aprovado. Smoke real do Playwright atualizado com Chromium headless e execucao JavaScript aprovado. Coletas reais acima validaram Patchright/Scrapling 0.5.1.
- Arquivos desta etapa: requirements.txt; README.md; CONTINUIDADE.md; scraping/transport.py; scraping/public_sources.py; scraping/peripherals.py; scraping/tech_stores.py; scraping/periodic.py; catalog_expansion/rotation.py; scripts/collect_peripherals.py; tests/test_collect_sample.py; tests/test_peripherals.py. Sem migracao, commit, push ou publicacao.


## 2026-11-12 - Dados de teste no banco existente e execucao local

- Por instrucao do operador, reutilizado hunter_dev da stack Docker local hunter-dev-scrapling; nao foi criado outro banco nem alterado o PostgreSQL nativo do Windows.
- Importacao via psql dentro de hunter-dev-scrapling-postgres-1, em transacao com verificacao de current_database(), a partir dos dois relatorios de coleta. 250 produtos coletados: 50 de KaBuM, Pichau, TerabyteShop, Amazon Brasil e Fast Shop. Preservados preco, imagem, origem e data real da coleta.
- Antes: 3 produtos/3 observacoes. Inseridos 249 produtos novos (um link ja existia) e 250 observacoes. Depois: 252 produtos/253 observacoes. Nenhuma remocao ou sobrescrita dos registros existentes.
- Reimportacao psql verificada: contagens inalteradas; sem duplicar produtos ou observacoes. SQL reexecutavel e relatorio local ignorados pelo Git em local-reports/import-peripherals-20261112.sql e local-reports/runtime-import-20261112.json.
- Verificacoes realizadas: health/ready, frontend, lojas e busca HTTP retornaram 200; busca por mouse encontra os dados importados nas quatro lojas novas. Teste visual Playwright confirmou busca pela homepage e filtro Amazon; captura em local-reports/runtime-search-20261112.png.
- Comando de execucao: .venv\Scripts\python.exe -B scripts/dev.py up --instance scrapling. Frontend/API pelo proxy local: http://localhost:18088. Coleta automatica permanece desativada na configuracao de desenvolvimento.
- Arquivo versionado atualizado nesta etapa: CONTINUIDADE.md. Sem alteracao de codigo ou esquema do banco.

- Reconstrucao Docker concluida; bootstrap terminou com sucesso, API/PostgreSQL/RabbitMQ saudaveis e worker/scheduler ativos. O frontend foi reiniciado para atualizar o upstream Nginx apos recriacao da API, corrigindo 502. Apos reinicio, health, frontend, lojas, busca e historico nas cinco lojas foram novamente aprovados.


## 2026-11-12 - Entrega em branch GitHub

- Branch: feat/coleta-multiloja-scrapling-stealth; base main/fae07c4. Commit de funcionalidade inclui transporte Scrapling/stealth, coleta multiloja/paginacao/categorias, validacao de imagens/precos, migracao 006, dependencias, testes e documentacao.
- Mantidas exatamente as alteracoes do operador relacionadas ao robots.txt, inclusive na documentacao e nas regras do projeto.
- Verificacoes desta entrega: 185 testes executados (119 aprovados, 66 ignorados por ambiente/integracao); Ruff global, qualidade Python/JavaScript e pip check aprovados; git diff --check sem erros. Auditoria de novas correspondencias sensiveis sem achados; os achados heuristicos anteriores correspondem a exemplos, fixtures e controles HTML.
- Dados importados, SQL de carga, capturas e relatorios em local-reports, configuracoes .env e credenciais locais permanecem ignorados e nao integram o commit. O PostgreSQL local com os dados de teste permanece inalterado nesta entrega.
