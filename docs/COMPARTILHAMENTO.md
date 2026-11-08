# Compartilhamento preparado ? sem publicacao

## Decisao

O repositorio original **NAO e apto para publicar seu historico**. A varredura de
blobs alcancaveis por todas as refs identificou segredo JWT em auth.py e URLs
PostgreSQL com senha nos dois scrapers antigos. Valores foram omitidos. A
continuidade registra rotacao anterior, mas isso nao torna o historico publicavel.
Nenhuma rotacao nova, reescrita de historico ou mudanca no banco foi feita aqui.

A estrategia e um **novo snapshot sem historico**, preservando integralmente
arquivos, .git, cofres, backups e volumes originais. A criacao de um novo repositorio,
primeiro commit e publicacao ficam para autorizacao futura. Nunca envie o .git
original, nem use git clone --mirror ou bundle para compartilhar este projeto.

## Pacote e arquivos

`python scripts/prepare_share.py` gera em dist/ um ZIP com pasta Hunter/ e arquivo
.sha256 ao lado. Nao executa git init/add/commit/push nem cria remoto. Cada execucao
gera nome novo. SHARE_MANIFEST.json enumera **todos os arquivos e seus hashes**.
O exportador inclui arquivos existentes rastreados e nao rastreados permitidos,
sem incluir os arquivos antigos removidos durante a reorganizacao. Nao e necessario
staging para preparar o pacote.

Inclui backend, config, frontend e imagens do projeto, messaging, catalog_expansion,
data_mining, scraping/parsers e fixture publica Pichau, migrations001?005, ops,
scripts, testes, CI, Dockerfiles/Compose, requirements, .env.example, ignores,
README, CONTRIBUTING, LICENSE e documentacao tecnica. A fixture Pichau e uma
captura publica antiga para teste de parser, nao um banco exportado nem precos
atuais; nao e importada pela stack dev. O texto CONTINUIDADE.md do pacote e um
resumo de equipe, sem inventario privado do operador; o original permanece intacto.

Exclui .git, .venv, caches, .env e .env.*, exceto .env.example, cofres DPAPI,
.secrets/secrets, chaves privadas, certificados locais, dumps/backups, bancos
SQLite, arquivos de credenciais, logs, relatorios locais, arquivos compactados e
volumes Docker. Segredos do historico tambem sao comparados com o conteudo do
snapshot; achado recusa a exportacao. O ZIP e seu checksum ficam ignorados.

O .gitignore evita novos arquivos sensiveis, mas nao remove os rastreados nem
limpa historico. A .dockerignore separa contexto de runtime dos testes/documentos.
O Dockerfile.test usa contexto adicional restrito a tests/ para incluir a suite.
Nao incluir arquivos privados nessa pasta.

## Auditoria

`python scripts/audit_sharing.py --history` examina candidatos atuais e todos os
blobs historicos alcancaveis por refs. Saida detalhada em
local-reports/sharing-audit.json, somente caminho, tipo e hash do objeto; nenhum
valor de segredo. Sao heuristicas, com falsos positivos/negativos: exemplos,
fixtures negativas e interpolacao de variaveis tambem podem ser sinalizados.
Foram revisados os achados atuais: placeholders de .env.example/documentacao,
interpolacao PowerShell, atributo HTML de senha e credenciais sinteticas em testes.
A URL com senha em documento legado foi substituida por placeholders.

Nao foram pesquisados backups/cofres privados para compor o compartilhamento.
Objetos Git inalcan?aveis/reflogs nao sao transportados, pois .git inteiro e excluido.
Uma futura auditoria de vulnerabilidades e licencas de dependencias e recomendada
antes de expor o sistema publicamente; esta validacao trata do compartilhamento
para desenvolvimento, nao de certificacao de seguranca em producao.

## Passo futuro dependente de autorizacao

Conferir o ZIP e seu manifesto, extrair em **nova pasta**, revisar o conteudo e
inicializar la um repositorio novo. Somente depois de autorizados, criar primeiro
commit, remoto e push. Nao modificar o .git original. Outro integrante podera entao
clonar a nova URL e seguir README.md. Nenhuma dessas acoes foi executada.

## Dados atuais separados

O snapshot Git continua sem dados pessoais, cofres ou backups. Para transferencia
integral de dados operacionais, usar exclusivamente o pacote .enc anonimizado e
a chave separada descritos em [TRANSFERENCIA_WINDOWS.md](TRANSFERENCIA_WINDOWS.md).
Nenhum envio e automatico. O manifesto do pacote do banco descreve o ponto de
consistencia e as transformacoes de privacidade.
