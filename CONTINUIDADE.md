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


## 2026-11-12 - App mobile React Native

- Nova branch local feat/app-mobile-react-native criada a partir de feat/coleta-multiloja-scrapling-stealth / 7cdd71e. Main e branch anterior preservadas; sem commit, push ou merge desta etapa.
- Novo cliente nativo em mobile/: React Native 0.88.1, Expo SDK 58, React 19.3 e TypeScript estrito. Navegacao nativa por abas e pilha; identidade visual verde/amarelo Hunter e icones vetoriais locais.
- Implementados catalogo real com busca/categorias/filtros/ordenacao/paginacao e cancelamento de buscas antigas; detalhe, imagens com fallback, condicoes, abertura segura da loja e historico; cadastro/login; alertas com criar/editar/excluir confirmado; notificacoes paginadas e leitura; perfil e configuracao da API.
- Usa os mesmos endpoints FastAPI e PostgreSQL existentes, sem credenciais do banco no app. JWT no SecureStore nativo, restauracao e expiracao de sessao, armazenamento serializado e isolamento de tokens por servidor. Troca de servidor encerra a sessao; formularios privados nao reaproveitam dados de sessao anterior. Builds de distribuicao exigem API HTTPS.
- Ponte opcional de desenvolvimento em scripts/mobile_api.py: so encaminha rotas conhecidas da API a um destino HTTP loopback, limita corpo, preserva autenticacao, nao registra corpos/tokens e nao serve arquivos, docs, PostgreSQL ou RabbitMQ. Cobertura em tests/test_mobile_bridge.py com backend HTTP ficticio.
- README principal e mobile/README.md explicam Expo Go, emulador, Wi-Fi/USB e builds. .dockerignore exclui mobile do build backend. CI ganhou job de TypeScript/testes/export Android-iOS. prepare_share inclui fontes mobile e exclui node_modules, .expo, dist e configuracoes locais, permitindo apenas o .env.example publico.
- Validacao: TypeScript aprovado; 11 testes mobile aprovados; 190 testes Python executados, 124 aprovados/66 ignorados; Ruff global e qualidade Python/JS aprovados; Expo Doctor 20/20; npm audit sem vulnerabilidades. Override restrito de minimatch 11.0.8 corrige o advisory transitivo do fingerprint Expo; fingerprint validado.
- Gerados bundles Hermes Android e iOS em mobile/dist, sem APK/IPA. Manifesto Expo Hunter Mobile, bundle Android de desenvolvimento e Metro/status HTTP 200 verificados. Cliente TypeScript consultou busca e historico nas cinco lojas reais pela API direta e pela ponte, sem gravar dados. O banco existente e seus produtos foram preservados.
- Execucao local ativa: Expo Metro exp://192.168.15.28:8081, com watch/reload; ponte API http://192.168.15.28:18089 para http://127.0.0.1:18088. mobile/.env.local configura a URL publica de desenvolvimento e permanece ignorado. QR em local-reports/hunter-mobile-expo-qr.png; relatorio em local-reports/mobile-validation-20261112.json, ambos locais/ignorados. Celular precisa estar na mesma rede e com Expo Go SDK 58.
- Limitacoes: nenhum dispositivo/emulador Android/iOS conectado para validacao visual nativa; APK/IPA assinado e publicacao nao realizados. Notificacoes sao in-app da API; push do sistema e sincronizacao offline nao configurados. Proxima verificacao: abrir o QR no aparelho e validar layout, teclado, login e alertas com a conta do operador.
- Arquivos desta etapa: mobile/ (configuracao, fontes, assets, lockfile, testes e guia); scripts/mobile_api.py; tests/test_mobile_bridge.py; .github/workflows/ci.yml; .dockerignore; scripts/prepare_share.py; README.md; CONTINUIDADE.md. Alteracoes anteriores do operador sobre robots.txt mantidas.

## 2026-11-12 - APK Android local

- Preparado build Android release de teste com JavaScript incluido, sem dependencia de Expo Go/Metro. Script reproduzivel em mobile/tools/build-apk.ps1, com URL da API como parametro e restauracao das variaveis do processo.
- Instalados SDK Android, build-tools 37.0.0, plataforma 37.0, NDK 27.1.12297006 e CMake 3.30.5 locais. Configuracao nativa gerada pelo Expo; sem edicao manual de arquivos Android, sem EAS/cloud, commit ou push.
- mobile/app.config.js e expo-build-properties habilitam cleartext apenas com HUNTER_APK_PREVIEW=1. O cliente release aceita HTTP privado/loopback apenas com EXPO_PUBLIC_LOCAL_PREVIEW=1; producao continua exigindo HTTPS. Credenciais do PostgreSQL nunca entram no APK.
- Alterados mobile/src/api/client.ts, mobile/src/lib/config.ts, AppProvider.tsx e AccountScreens.tsx para a politica de conexao; teste novo cobre redes privadas e rejeicao de HTTP publico. Adicionados ESLint/configuracao e instrucoes no guia mobile; removido BOM de App.tsx.
- Validacao previa: TypeScript e 12 testes aprovados; lint sem erros, com 20 avisos de adocao do React Compiler (compilador nao habilitado). API LAN /health/ready HTTP 200. Nenhum aparelho conectado no adb; validacao visual/fisica permanece pendente. Resultado final do APK registrado abaixo apos compilacao.
- Configurado plugin mobile/plugins/withShortCmakePaths.js para CMAKE_OBJECT_PATH_MAX=240 e staging curto em ~/.hcx/<hash-do-projeto>, evitando objetos com caminhos extensos no Windows/Ninja. Prebuild limpa/regenera apenas o Android criado nesta tarefa; variaveis sao restauradas ao terminar. AGP tambem instalou build-tools 36.0.0 e CMake 3.22.1 automaticamente.
- APK gerado: mobile/dist/hunter-mobile-preview.apk, 45.089.462 bytes (45,1 MB), pacote com.hunter.mobile / versao 1.0.0, Android 7+ (API 24), ARM64 e x86_64. JavaScript Hermes incluido (1.880.060 bytes) e URL da API LAN confirmada no bundle. Assinatura interna de teste; sem publicacao.
- SHA-256: 016ec06b9d56211a07ee1cd289b2a8cf8dad45b53b1abe47d725f99df6d1a639. apksigner verify aprovado (v2), zipalign com pagina de 16 KB aprovado, aapt leu pacote/SDKs e integridade ZIP aprovada. Build Android release e verificacoes lintVital concluidos. Relatorios locais em local-reports/hunter-apk-*; APK e relatorios ignorados pelo Git.
- Teste de leitura da API LAN repetido e aprovado nas cinco lojas, incluindo busca/historico. API precisa continuar em execucao e o celular na mesma rede; nao depende de Metro/Expo Go. Sem aparelho no adb para validar instalacao/layout/autenticacao real. Banco e dados existentes preservados; sem commit ou push.
- Arquivos desta etapa APK: mobile/package.json, package-lock.json, app.json, app.config.js, eslint.config.js, App.tsx (BOM), src/api/client.ts, src/lib/config.ts, src/context/AppProvider.tsx, src/screens/AccountScreens.tsx, tests/client.test.ts, tools/build-apk.ps1, plugins/withShortCmakePaths.js, README.md; CONTINUIDADE.md. Demais alteracoes da etapa mobile anterior mantidas.

## 2026-11-12 - Envio da branch mobile ao remoto

- Entrega autorizada da branch feat/app-mobile-react-native: cliente nativo, ponte API, testes/CI, documentacao e build APK local. Excecao em mobile/.gitignore inclui src/lib/*.ts apesar do ignore Python global; configuracao local .claude permanece fora do Git.
- Validacoes da entrega: APK release compilado, assinatura/alinhamento/integridade aprovados; TypeScript e 12 testes mobile aprovados; lint sem erros (20 avisos); Expo Doctor 20/20; leitura real nas cinco lojas aprovada. Verificacao de diff e auditoria dos arquivos staged antes do commit. Teste em aparelho fisico pendente.
- APK, node_modules, pastas Android/iOS geradas, .env locais e relatorios nao integram o commit. Sem alteracao do banco, das regras robots.txt ou da main.

## 2026-11-12 - Analise de instalacao pelo colaborador

- origin/main conferida apos fetch: fae07c4; ainda sem coleta atualizada/mobile. Branch remota feat/app-mobile-react-native em b463ddf inclui as atualizacoes anteriores, app e arquivos src/lib necessarios. Nenhum merge realizado nesta analise.
- Compose dev da main e da branch validado com segredos efemeros em memoria, sem iniciar containers nem acessar/alterar dados. API/bootstrap usam postgres:5432/hunter_dev com credencial consistente; PostgreSQL sem porta publicada e API depende do bootstrap concluido. Em instalacao nova, configure gera segredos locais e up cria volume/banco proprio; dados do operador nao viajam pelo Git. Em volume existente, up preserva dados e aplica a nova migracao 006; SQLs 001-005 nao mudaram entre main e branch.
- Pendencias identificadas, sem correcao de codigo automatica: README ainda pede URL de repositorio novo; mobile/README.md, .env.example, fallback do app e ponte usam porta 18088 da instancia do operador, enquanto configure padrao gera 8088. Para instalacao padrao, ponte deve receber --target http://127.0.0.1:8088 e o app deve usar o IP/porta da ponte do colaborador. APK atual inicia com IP privado do operador; URL pode ser alterada em Conta > Conexao.
- Compartilhar os mesmos dados entre computadores exige uma API central publicada e configuracao HTTPS no app; pull nao sincroniza PostgreSQL. Producao exige DATABASE_URL de runtime, TLS verify-full, broker AMQPS e segredo JWT externos. Coleta dev vem desligada; instalacao nova recebe apenas oferta ficticia, nao os 250 produtos coletados.
- Validacao limitada a leitura dos fontes/refs e docker compose config nas duas versoes; nao foi simulada uma instalacao limpa completa. Nenhum dado, segredo, servico ou regra robots.txt alterado. Apenas este registro documental foi modificado; sem commit/push desta analise.

## 2026-11-12 - Integracao na main e guia do colaborador

- Integradas na main, por merges sem conflitos e sem apagar branches, feat/coleta-multiloja-scrapling-stealth e feat/app-mobile-react-native. A ancestralidade das duas branches remotas foi conferida; fontes funcionais e alteracoes robots.txt preservadas. Registro anterior de analise preservado em commit proprio antes dos merges.
- Criado docs/GUIA_COLABORADOR.docx, guia de tres paginas para Windows/PowerShell com mensagens prontas ao agente em sete passos: requisitos/clone, configuracao e bootstrap Docker, acesso psql nao interativo, testes e coleta opcional, mobile pela ponte, APK e atualizacao preservando dados. Explica bancos locais separados e necessidade de API HTTPS central para dados compartilhados. Nao inclui credenciais nem dados privados.
- README.md atualizado para o repositorio real e link do Word; mobile/README.md documenta explicitamente porta 8088 em instalacao nova e --target da ponte. Mantidos os exemplos 18088 da instancia do operador, sem alterar configuracao de runtime nem reconstruir APK desnecessariamente.
- Validacoes pos-merge: 190 testes Python executados (124 aprovados, 66 ignorados); TypeScript e 12 testes mobile aprovados; lint mobile sem erros/20 avisos ja conhecidos; Ruff e qualidade Python/JS aprovados. Consultas psql de leitura confirmaram hunter_dev e migracoes ate 006 na instancia existente; CLI collect_sample --help aprovado. Nenhuma coleta, carga ou alteracao no banco foi executada nesta entrega.
- Word gerado com dependencias gerenciadas, renderizado via LibreOffice para PDF/PNG e tres paginas revisadas visualmente; removida borda decorativa do titulo. Relatorios, renderizacoes e ferramentas auxiliares ficam em local-reports, ignorados. Instalacao em outro computador e teste fisico do app permanecem dependentes do ambiente do colaborador.
- Arquivos adicionais desta entrega: README.md, mobile/README.md, CONTINUIDADE.md e docs/GUIA_COLABORADOR.docx. Commit documental e push da main autorizados pelo pedido de integracao; branches de origem mantidas.

## Instalacao da main do colaborador em 12/11/2026
- Lido GUIA_COLABORADOR.docx fornecido pelo usuario. Main remota atualizada em 0a244ab, com merges de scraping e mobile.
- Clone separado em local-data/Hunter-main; instalacao original e bancos anteriores preservados. Sem commit ou push.
- Criada configuracao ignorada .env.dev.main.local; stack independente hunter-dev-main em http://localhost:8088. Usar --instance main nos comandos scripts/dev.py configure/up/status/stop nesta copia.
- Python 3.12.2 da venv original usado apenas para helper de biblioteca padrao; py -3.12 no sandbox nao encontrou instalacao. Docker build e dependencias concluidos.
- Novo volume PostgreSQL hunter-dev-main_dev_postgres e RabbitMQ independente. Baseline inicializado e migracoes 002 a 006 confirmadas por SELECT; nenhum banco existente alterado.
- Smoke do guia aprovado: frontend, cadastro/login, busca ficticia, alerta, scheduler/broker/worker, notificacao/leitura e Data Mining demo. CLI collect_peripherals --help aprovada sem coleta externa.
- Dados reais e contas antigas nao foram transferidos; esta stack contem oferta DEMO FICTICIO e usuario/alerta do smoke. Coleta automatica desligada. Navegadores para coleta e mobile/APK nao preparados nesta etapa; sem nova captura/importacao de produtos.
- Arquivos alterados: CONTINUIDADE.md nas duas copias e configuracao local ignorada na nova. Codigo clonado preservado. Nova copia deve ser usada como raiz no desenvolvimento da main.

## Captura multiloja e teste da main em 12/11/2026
- Coleta autorizada: scripts/collect_peripherals.py --target 50 --max-pages 5, transporte auto original, sem alterar fontes versionados. Relatorio UTC peripherals-20261113T014433544873Z.json (noite de 12/11 local).
- Capturadas e importadas na stack hunter-dev-main: KaBuM! 50, Pichau 50, TerabyteShop 50, Amazon Brasil 50, Fast Shop 50. Total 250 produtos e 250 observacoes reais datadas.
- Mercado Livre: zero, redirect para verificacao de conta. Magalu: zero, HTTP 403. GK InfoStore: zero, HTTP 423/loja indisponivel. Fontes interrompidas, sem insistencia/proxy/resolucao de desafios ou dados ficticios para completar metas.
- Fast Shop: 50 ofertas sem imagem fornecida pelo parser; 200 ofertas das outras lojas com imagem. Interface usa placeholder explicito. Limitacao pendente para proxima etapa; nenhum URL de imagem inventado.
- Instalados Chromium Patchright e bibliotecas Linux dentro do container API, cache /tmp/hunter-browsers. Instalacao e efemera: reconstruir/recriar o container exige preparar navegador novamente. Coleta automatica continua desligada.
- Importacao por helper local ignorado local-reports/import_capture.py, reutilizando normalize/save_observations, guarda postgres/hunter_dev, transacao e lock; dados anteriores preservados. Primeira tentativa parou antes da conexao por exigir imagem em todas as ofertas; validacao ajustada para aceitar campo opcional conforme contrato existente.
- Confirmados por SQL 50 produtos em cada uma das cinco lojas e 250 observacoes. Reimportacao do mesmo lote dentro da transacao adicionou zero observacoes; idempotencia aprovada.
- Testes: 14 de perifericos + 20 de coleta aprovados; pip check sem conflitos; smoke_dev aprovado (login, busca demo, alerta, fila/notificacao, Data Mining). Verificacao HTTP e navegador real nas cinco lojas: busca/filtro, preco ascendente, datas e historico aprovados; desktop/mobile sem overflow e sem erros JavaScript. Capturas PNG revisadas.
- Relatorios, JSON original, resultado de importacao, verificacao e screenshots em local-reports/capture-20261112; helpers import_capture.py e verify_capture.py em local-reports, ignorados pelo Git.
- Arquivos versionados alterados apenas CONTINUIDADE.md (nova copia e registro na original); configuracoes/segredos nao expostos. Sem commit/push, DDL ou acesso ao banco antigo. Aplicacao atualizada em http://localhost:8088/index.html.

## Correcao das imagens Fast Shop em 12/11/2026
- Inspecao real da listagem publica identificou img[data-fs-product-card-image] fora do anchor do titulo. Helper generico exigia imagem dentro do link e descartava todas.
- scraping/tech_stores.py agora aceita fallback apenas do mesmo card Fast Shop, imagem marcada, alt exatamente igual ao nome do produto e URL validada. Imagens de botoes, produto diferente ou multiplas URLs ambiguas rejeitadas; regras das demais lojas preservadas.
- tests/test_peripherals.py inclui regressao de foto fora do link, nome diferente, botao de favorito e ambiguidade. 49 testes de perifericos/coleta/parsers aprovados. Nenhuma dependencia nova.
- Recapturadas 50 ofertas Fast Shop: 50 imagens reconhecidas. Importadas como 50 NOVAS observacoes pelo helper validado, sem sobrescrever as anteriores. Banco permanece 250 produtos, agora 300 observacoes; consulta dos ultimos registros confirma 50 Fast Shop com imagem.
- Reimportacao idempotente aprovada. Busca, filtro, ordenacao, historico, desktop/mobile e ausencia de erros JS aprovados; navegador confirmou carregamento de foto real. Smoke login/busca/alerta/fila/notificacao/Data Mining aprovado. Consulta auxiliar teve referencia id ambigua; corrigida com aliases e conferida por SELECT, sem escrita nessa consulta.
- Correcao fonte copiada ao container API para coleta imediata; tambem permanece no checkout para proximos builds. Sem reconstruir container nesta etapa para preservar Chromium efemero ja instalado.
- Mercado Livre (verificacao de conta), Magalu (403) e GK (423/indisponibilidade) continuam pendentes conforme diagnosticos reais anteriores; nao repetidas sondagens nem declarados corrigidos sem evidencia. Nao houve proxy ou resolucao de desafios.
- Evidencias ignoradas em local-reports/fastshop-fix-20261112 (JSON, HTML diagnostico e screenshots); helper local verify_capture.py ampliado para verificar carregamento da foto.
- Arquivos versionados alterados nesta etapa: scraping/tech_stores.py, tests/test_peripherals.py e CONTINUIDADE.md. Registro tambem adicionado a continuidade da instalacao original. Sem commit/push, DDL, exclusao de dados ou alteracao do banco antigo.

## Publicacao da correcao na main em 12/11/2026
- Usuario autorizou commit e push e escolheu integracao direta na main compartilhada; nao ha main separada por colaborador no remoto.
- Fetch confirmou HEAD igual a origin/main antes da entrega (0a244ab). Correcao Fast Shop, teste de regressao e registros de continuidade revisados; 49 testes aprovados novamente e diff --check sem erros.
- Somente scraping/tech_stores.py, tests/test_peripherals.py e CONTINUIDADE.md integram esta entrega. Configuracoes locais, segredos, dumps, relatorios e dados PostgreSQL permanecem fora do Git.
- Atualizacao dos colaboradores: com alteracoes locais preservadas, git pull --ff-only origin main e reconstruir a stack existente com scripts/dev.py up e o mesmo --instance usado na configuracao. Nao regenerar senhas nem apagar volumes; Git sincroniza codigo, nao bancos locais.

## Encerramento em 12/11/2026
- A pedido do usuario, parados os dez containers Hunter ativos (main, simulacao e RabbitMQ original) com docker stop, preservando containers e volumes.
- Encerrados API, frontend, worker e scheduler locais identificados no inventario HunterRuntime, incluindo processos Python filhos.
- Verificacao: docker ps sem containers ativos e nenhuma porta em escuta em 5500, 8000 ou 8088. Sem exclusao de dados, alteracao de codigo, commit ou push.
- Arquivos alterados nesta tarefa: apenas CONTINUIDADE.md nas duas copias. Testes funcionais nao executados por se tratar de encerramento; verificacao operacional concluida.
- Retomar amanha em local-data/Hunter-main; iniciar a stack pelo helper scripts/dev.py up --instance main com o ambiente Python existente. Pendencias de desenvolvimento registradas acima permanecem.

## Inicializacao local em 14/11/2026
- Retomada autorizada da nova versao local-data/Hunter-main; Git conferido, com alteracao preexistente apenas em CONTINUIDADE.md, preservada.
- Docker Desktop iniciado e seis containers existentes hunter-dev-main retomados, sem rebuild, bootstrap ou migracoes. Volumes e dados preservados; instalacao original nao iniciada.
- PostgreSQL, RabbitMQ, API e frontend healthy; worker conectado e scheduler com ciclos concluidos. Falhas AMQP transitorias durante partida resolvidas automaticamente pela reconexao.
- HTTP 200 em index.html, buscar.html, docs, health/ready e analytics/estatisticas?origem=demo. Aplicacao em http://localhost:8088/index.html.
- Coleta externa permanece desligada. Nenhuma alteracao de codigo, commit, push ou exclusao de dados. Apenas este CONTINUIDADE.md atualizado; suite completa nao repetida por se tratar de inicializacao operacional.

## Mineracao em streaming em 14/11/2026
- Implementado consumidor continuo independente data_mining.streaming, fila hunter_dev.analytics e DLQ separadas dos alertas. Trigger/outbox transacionais por nova observacao, publicacao confirmada, ACK apos commit, retry limitado e resultados idempotentes por observation_id.
- Tecnica: janela deslizante por contagem de ate 20 observacoes, media/min/max, variacao, queda >=5% e z-score contra baseline anterior com criterios de suficiencia. Consulta dos resultados persistidos em GET /analytics/streaming; K-Means e endpoints anteriores preservados.
- Backup privado ignorado antes de DDL. Migracoes incrementais 007/008 aplicadas na nova instancia, sem modificar migracoes existentes. 008 inclui fontes scrapling_browser_card/scrapling_public_card, tambem reconhecidas pelo Data Mining anterior.
- Conferencia: 250 produtos e 300 observacoes preservados; 300 eventos processed e 300 resultados replay=true. Um consumidor ativo na fila analitica, sem backlog nem DLQ. Nenhuma coleta externa ou fixture sintetica inserida no banco da aplicacao.
- Validacao final: 205 testes sem skips, cobertura global 83%, Ruff/diff --check/builds aprovados; demo com processo consumidor independente recebeu 100->80, persistiu dois resultados novos replay=false e resistiu a duplicata. Regressao RabbitMQ e navegador desktop/mobile aprovada no isolado. HTTP 200 em frontend/docs/ready/streaming/estatisticas real/demo.
- Corrigidos libatomic1 nas imagens e fixture antiga de rotacao sensivel a IDs/relogio; sem mudar regras de coleta. CI inclui demo streaming, execucao remota nao verificada. Sem commit/push.
- API atualizada por copia/reinicio para preservar Chromium efemero; analytics usa imagem nova. Mudancas fonte e bootstrap/Compose permitem proximos builds. Servicos da aplicacao permanecem ativos; testes parados preservando volumes.
- Relatorio com inventario completo, limites e evidencias: docs/VALIDACAO_STREAMING.md. Roteiro de prova: docs/MINERACAO_STREAMING.md. Logs e JSON ignorados: local-reports/streaming-20261114. Configuracoes novas de teste ignoradas; segredos nao documentados.
- Apenas a copia local-data/Hunter-main foi alterada. Instalacao original preservada. Proximas etapas PLN/desktop/Azure nao iniciadas.

## PLN e autocomplete em 14/11/2026
- Conferencia encontrou somente autocomplete nativo de formularios, sem sugestoes de produtos. Implementado PLN de titulos publicos em nlp: limpeza HTML, normalizacao Unicode/acentos, tokens, stopwords portugues, palavras-chave e classificacao tematica por regras explicitas; algoritmo titulo-regras-pt-v1. Sem modelo treinado ou processamento de feedback privado.
- Migracao incremental 009 adiciona hunter_nlp_events/hunter_text_results e trigger/outbox atomicos. Fila hunter_dev.nlp e DLQ com consumidor independente; infraestrutura de streaming compartilhada com parametros restritos e contratos anteriores preservados.
- Novas rotas /nlp/analises, /sugestoes e /analytics/categorias associam texto e resultado numerico do mesmo evento. Autocomplete na home/busca com teclado, debounce, cancelamento, protecao contra resposta atrasada/XSS e falha sem bloquear busca livre.
- Validacao: 217 testes sem skips, cobertura global 83%; demo com processos independentes, banco/broker reais e fixture isolada replay=false comprovou texto e mineracao integrados/idempotentes. Regressao anterior e navegador desktop/mobile aprovados. Ruff, sintaxe Python/JS, builds e diff --check aprovados; CI atualizada, execucao remota nao verificada.
- Instalacao: backup privado ignorado antes da 009. 250 produtos, 300 observacoes e 300 resultados numericos preservados; 300 resultados PLN replay=true. Consumidor nlp ativo, backlog/DLQ vazios. Proxy Nginx ajustado para novas rotas, nginx -t e navegacao instalada via Edge headless aprovados. API copiada/reiniciada para preservar Chromium efemero; frontend/nlp em imagens novas.
- Evidencias JSON/logs/capturas reais revisadas em local-reports/nlp-20261114, ignorado. Documento com roteiro, limites e inventario: docs/PLN_AUTOCOMPLETE.md. Relatorio global de linhas nao equivale a precisao do classificador; avaliacao em corpus real rotulado permanece futura.
- Apenas nova copia alterada; instalacao original preservada. Sem coleta externa, exclusao de dados, commit/push ou implementacao de desktop/Azure. Servicos da aplicacao permanecem ativos; containers de teste parados, volumes preservados.

## Qualidade TDD e preparacao de publicacao em 14/11/2026
- Usuario autorizou consolidar evidencias de TDD/CI e atualizar o GitHub. Fetch confirmou main remota na base 895b79e; acesso REST autenticado confirmado sem exibir/gravar credencial. Execucao anterior 43354598188 dessa base concluida com sucesso, sem confundir com as novas alteracoes.
- Entregas anteriores de streaming/PLN consolidadas no commit local 9367d25. Auditoria verificou nove valores secretos locais contra arquivos compartilhados sem achados; arquivos de ambiente, backups e relatorios privados permanecem ignorados.
- Ciclo TDD real novo: 8e328d1 RED com teste de combo mouse/mousepad falhando; 1286f53 GREEN com correcao minima; c04b52d REFACTOR com regra extraida e mesmo teste aprovado. Evidencias com hashes/comandos/horarios em docs/evidence/tdd-combo; escopo restrito a esse caso, sem alegacao de TDD retroativo de todo o projeto.
- CI preparada para guardar logs, cobertura XML/JSON, resumo por SHA/run, demos e capturas isoladas como artefatos com retencao de 30 dias. Segredos efemeros mascarados. Nenhum dump/arquivo de login da demo e enviado.
- Documentacao em docs/TDD_QUALIDADE.md e fluxo em CONTRIBUTING.md. Regressao local atual e nova execucao remota serao conferidas antes do encerramento; nao ha resultado remoto das novas alteracoes neste registro.

## Publicacao e CI comprovadas em 14/11/2026
- Push normal autorizado publicou a main ate d59198c, incluindo streaming, PLN, autocomplete, ciclo TDD e artefatos CI. Sem force-push ou alteracao da instalacao original.
- Actions 43563594614 concluido success no SHA d59198c1748f25ea9c479c7c2f618d6f552a4adf: validate e mobile aprovados. URL https://github.com/souzaoryon3/Hunter/actions/runs/43563594614.
- Conferidos artefatos baixados: 218 testes backend/integracao sem skips em 12,666s; 2474/2969 linhas, 83,3277% de cobertura (minimo80). Mobile: 12 testes pass, zero falhas/skips, TypeScript/Expo/bundles Android/iOS aprovados. Demos e navegador passaram.
- Artefatos hunter-quality-43563594614-1 e mobile-tests-43563594614-1, retencao30 dias. Registro selecionado permanente em docs/evidence/ci/run-43563594614.json; logs/ZIP privados em local-reports/ci-20261114. Antes da publicacao final, testes.log/demos sao sanitizados contra segredos efemeros, alem de mascaramento do console.
- Correcao TDD do consumidor NLP ativada em imagem nova para novas analises; resultados historicos preservados. Testes locais finais:218 sem skips,83%; servicos de teste parados preservando volumes, aplicacao principal ativa.
- docs/TDD_QUALIDADE.md documenta prova e limites: TDD comprovado para novo caso mouse/mousepad, nao todo legado; CI nao equivale a protecao de branch, teste fisico mobile ou deploy Azure. Relatorio final segue em commit de evidencias, que gerara nova execucao automatica.

## 2026-11-16 - Atualizacao da main local (0a244ab -> 07905f8)

- Release de restauracao publicada antes da atualizacao: tag hunter-pre-update-20261116 no commit 0a244ab, apenas codigo-fonte, sem backup de banco, credenciais ou chaves; nao marcada como Latest.
- origin/main validada em worktree temporario antes do pull; pull fast-forward de 7 commits (mineracao streaming, PLN/autocomplete, evidencias TDD/CI, imagens Fast Shop).
- Validacao apos o pull (.venv, Python 3.11): Ruff e check_quality aprovados; unittest discover -s tests: 218 executados, OK, 81 ignorados por dependerem de PostgreSQL/RabbitMQ de teste. Docker Desktop parado, integracao local nao executada; CI GitHub 43564094545 aprovado com integracao no mesmo commit.
- Migracoes autorizadas pelo operador e aplicadas no hunter_dev da stack hunter-dev-scrapling. Backup previo pg_dump -Fc em local-reports/backup-hunter_dev-pre-007-20261116.dump (ignorado; 20 tabelas com dados, listagem pg_restore conferida).
- Aplicacao via .venv\Scripts\python.exe -B scripts/dev.py up --instance scrapling: imagens reconstruidas, bootstrap aplicou 007, 008 e 009 sem remover dados; servicos novos analytics e nlp iniciados e saudaveis.
- Verificacao: hunter_schema_migrations 002-009; 253 observacoes e 252 produtos preservados; replay concluido com 253 eventos analytics e 253 eventos PLN processados, 253 resultados em cada tabela. /health/ready, /sugestoes?q=mouse, /analytics/categorias e /nlp/analises retornaram 200 em http://localhost:18088.
- ops/postgres_roles.sql nao aplicado: a stack dev usa o proprietario hunter_dev e os grupos hunter_runtime/hunter_migrator nao existem nesse banco; grants so se aplicam a ambientes com papeis minimos.
- Sem commit ou push de codigo nesta etapa.

## 2026-11-16 - Integracao Azure para entrega academica (branch feat/azure-entrega)

- Branch feat/azure-entrega criada a partir da main 07905f8. Integracao opcional: sem .env.azure.local nada muda na stack.
- Codigo novo: modulo cloud/ (config, mensagens, storage Blob/Queue, worker de exportacao, telemetria OpenTelemetry), scripts/azure_backup.py, tests/test_cloud.py, docs/AZURE.md, infra/azure/ (provision.ps1, lifecycle-policy.json, workbook.json). Alterados: backend/main.py (instrumentacao condicional), compose.dev.yaml (APPLICATIONINSIGHTS e servico azure-export no perfil azure), scripts/dev.py (inclui .env.azure.local e perfil azure quando existir), requirements.txt (azure-storage-blob 12.31.1, azure-storage-queue 12.18.1, azure-monitor-opentelemetry 1.8.12).
- Azure CLI instalada (winget) e autenticada por device code na assinatura Azure for Students. Politica da assinatura permite somente eastus, centralus, northcentralus, southcentralus e mexicocentral; usado eastus.
- Recursos em rg-hunter-entrega: storage sthunter26143 (ZRS, TLS 1.2, sem acesso publico, versionamento, soft delete 14 d, ciclo de vida), containers backups/exportacoes, filas hunter-exportacoes(-poison), Log Analytics law-hunter (30 d, 0,5 GB/dia), Application Insights appi-hunter, 3 alertas de metrica e workbook "Hunter - Monitoramento do ambiente". VM provap2 de outro trabalho permaneceu desalocada e nao foi usada.
- Incidente: o cmd do Windows ecoou a connection string do Storage no log da sessao; as duas chaves foram rotacionadas e .env.azure.local atualizado sem exibir valores. Docs orientam usar --auth-mode key.
- Testes: 228 testes Python OK (81 ignorados por integracao), 10 novos; Ruff e check_quality aprovados. Azure: 2 backups (24 tabelas) enviados e verificados com SHA-256 e pg_restore; 3 exportacoes (252 produtos) via fila; mensagem invalida desviada para poison; telemetria da API (requisicoes, 422 propositais, latencia) visivel no Application Insights e no workbook.
- Correcao: amostragem fixada em 100% (sampling_ratio=1.0); o padrao limitava por segundo e perdia rajadas. Logs HTTP do SDK silenciados.
- Documento ABNT (22 paginas, capturas do portal) em local-reports/azure/Hunter_Azure_ABNT.docx/.pdf, ignorado pelo Git por conter o e-mail da conta nas capturas; geradores em local-reports/azure/gerador. Campos de identificacao (instituicao, curso, aluno, professor, cidade) ficaram entre colchetes para preenchimento.
- Pendente: commit/push da branch (nao autorizados); agendamento diario do backup (descrito, nao agendado); excluir rg-hunter-entrega ao fim da disciplina.
