# Rotacao persistente e suporte multiloja — Etapa 2

## Entrega e ativacao

004 e 005 aplicadas no hunter_db:5432 em 07/11/2026 depois de teste isolado,
backup custom verificavel por pg_restore --list e comparacao de fingerprints dos
campos anteriores. Os seis produtos, IDs, imagens e12 observacoes foram preservados.
005 adiciona registro de lojas, canal, condicoes promocionais, quotas, controle de
rodada e heartbeat. A lista fixa CHECK de lojas do catalogo foi substituida por FK
ao registro de lojas. Nenhuma tabela/dado foi removido ou reconstruido.

Fonte KaBuM vinculada aos seis IDs existentes, sem novas observacoes e sem coleta
forcada. O bootstrap e idempotente e conserva o maior prazo entre historico,
journal anterior e estado persistente. Nao altera cooldowns para adiantar visitas.
Mercado Livre/Pichau e novas lojas nao foram habilitados.

## Regras da rotacao

- Um scheduler por banco: advisory lock281236 mantido em conexao dedicada durante
  toda a instancia. Perda dessa conexao encerra a instancia antes de novo scan.
- Coleta continua como tarefa do scheduler existente, fora do loop de alertas.
  Lock281235 tambem impede concorrencia com o coletor anterior.
- Sem limite de seis candidatos cadastrados. Cada rodada processa no maximo seis
  produtos; proxima rodada so apos pelo menos seis horas. Mais produtos implicam
  revisitas potencialmente superiores a seis horas.
- Selecao por next_attempt_at mais antigo e ID, com FOR UPDATE SKIP LOCKED,
  travando candidato/fonte, e lease UUID. Tentativa, quota e inicio da primeira
  rodada sao persistidos antes de HTTP; crash nao recupera orçamento consumido.
- Quota por fonte e janela (minimo6h): request_limit conta consultas a produtos;
  http_request_limit conta reserva conservadora de requisicoes HTTP. O adaptador
  atual reserva duas por consulta: robots.txt e pagina. Mesmo falha no robots
  consome as duas reservas, protegendo o limite. Default6 produtos/12 HTTP.
- Espera configurada entre requisicoes robots/produto e entre produtos. Nao ha
  retries internos nem redirecionamentos seguidos. Todos os futuros adaptadores
  precisam respeitar o contrato de no maximo duas requisicoes ou ganhar politica
  de reserva especifica ANTES de serem registrados/habilitados.
- 429 suspende fonte pelo maior entre backoff,24h e Retry-After (segundos ou data
  HTTP). 401/403/robots/desafio/redirecionamento bloqueiam a fonte, exigindo revisao
  explicita; nao reativar automaticamente para tentar contornar protecoes.
- Fontes sem permission_reference ou adaptador implementado nao sao processadas.
  A referencia e registro administrativo, nao comprovacao automatica de licenca.
  Somente paginas pontuais KaBuM ja monitoradas foram ativadas nesta entrega.
- HTTP executa em thread, sem transacao aberta. Antes de gravar, identidade,
  imagem HTTPS, canal e lease sao validados; observacao, produto associado e
  resultado da execucao fazem commit juntos. Fencing recusa donos antigos.
- Repeticao com timestamp/fonte identicos nao cria observacao. Novas observacoes
  reais com preco igual sao preservadas sem inventar variacao. Alertas continuam
  usando a regra existente de transicao; testes verificam ausencia de repeticao.

## Heartbeat e diagnostico

Tabela hunter_scheduler_heartbeat contem instancia, PID efetivo, inicio, ultimo
sinal, ultima/maior lacuna e diferenca entre relogio civil e monotonic. Logs novos
incluem timestamp UTC. Heartbeat e atualizado a cada ciclo de alertas (principal:
10segundos); coleta supervisionada a cada60segundos. Instante da proxima coleta
depende tambem das quotas, cooldowns, elegibilidade e disponibilidade do host.
O heartbeat e diagnostico, nao executor de reposicao: periodos de suspensao nao
geram observacoes retroativas. Recuperacao de lease nao antecipa as seis horas.

## Multiloja e precos

`/lojas` fornece lojas cadastradas; API e seletor da busca aceitam o registro
extensivel. Opcoes legadas permanecem como fallback da interface. Registrar uma
loja nao a torna uma fonte autorizada ou uma oferta atual.

Produto possui channel retail/b2b; observacao possui price_kind regular/promotional
e promotion_terms (obrigatorio para promocao). Mesmo link nao troca de canal
silenciosamente: exige oferta distinta. Busca, alertas e Data Mining padrao usam
varejo; B2B nao e misturado implicitamente. Historico informa canal/condicoes e
cards exibem condicao promocional quando fornecida pela fonte.

`catalog_expansion.adapters` define FetchResult e registro de adaptadores. So
kabum_public esta implementado; seu contrato recusa outra loja, categoria ou host.
Novas APIs/feeds exigem acesso, permissao de exibicao/retencao/analise, schema,
quotas e credenciais via ambiente/secret manager, nunca nos registros ou logs.
Revisar tambem REAL_SOURCES de Data Mining ao adicionar nova proveniencia legitima.
Nao ha equivalencia entre ofertas de lojas diferentes inferida pelo nome.

## Operacao segura

Scripts administrativos nao executam coletas e recusam destino diferente do
principal local confirmado. Em terminal novo, sem ambiente de testes ativo:

```powershell
. .\scripts\queue_environment.ps1
.venv\Scripts\python.exe -B scripts/catalog_stage2.py inspect
# As acoes abaixo sao explicitas; nao repetir apenas para conferir estado:
.venv\Scripts\python.exe -B scripts/catalog_stage2.py migrate
.venv\Scripts\python.exe -B scripts/catalog_stage2.py seed
.venv\Scripts\python.exe -B scripts/catalog_stage2.py restart
# Reiniciar apenas scheduler, quando necessario:
.venv\Scripts\python.exe -B scripts/catalog_stage2.py restart --scheduler-only
```

`migrate` cria backup fora do repositorio antes do executor oficial. Arquivos ficam
em %TEMP%\HunterBackups: transferir para armazenamento duravel protegido.
`restart` adquire lock de coleta ou recusa; valida comandos/PIDs/filhos antes de
qualquer parada. Console conhost do Windows e reconhecido e nao encerrado
explicitamente. Fecha somente API/scheduler necessarios, preservando worker,
RabbitMQ e frontend. Transacoes interrompidas fazem rollback; eventos outbox
permanecem recuperaveis. Novos logs stage2-* e PIDs ficam em HunterRuntime.

## Evidencias, limites e proxima etapa

Testes isolados incluem oito candidatos: seis consultados na primeira rodada,
zero repetidos ao chamar novamente, dois restantes apos simular rodada seguinte.
Cobrem quotas HTTP/produto, bloqueios, Retry-After, concorrencia, lease expirado,
heartbeat/ajuste de relogio, importacao idempotente, lojas dinamicas, B2B e alertas.
Precos/produtos sinteticos desses testes existem somente no banco isolado.

Principal continua com seis produtos reais de uma loja (KaBuM), seis imagens e12
observacoes na ativacao. Nao ha 30 produtos nem tres lojas novas demonstradas.
Faltam URLs adicionais verificadas e autorizacoes/conectores reais de outras
lojas. Nao houve descoberta automatica, scraping em massa ou ativacao de API B2B.
Validacao binaria/licenca de novas imagens deve integrar a futura admissao; nesta
etapa as seis imagens existentes foram novamente comprovadas no Edge.

Matching de SKU, aliases persistentes de URL, autorizacao comercial automatica,
alta disponibilidade e renovacao de leases para adaptadores longos ficam fora
desta entrega. Atual adaptador possui timeouts menores que seu lease de300segundos.
