# Coleta periódica limitada do Hunter

Atualizacao Etapa2 (07/11/2026): o principal usa fila persistente004/005, rotacao,
quotas e heartbeat. A lista JSON abaixo e bootstrap/fallback legado; o limite de
seis agora se aplica a rodada, nao ao cadastro. Estado e operacao atuais em
[ROTACAO_CATALOGO.md](ROTACAO_CATALOGO.md). Nao editar/apagar journal para forcar coleta.

Ativa no scheduler local em 07/11/2026. Não há agendador adicional, migração nova,
scraper em massa ou alteração destrutiva. A primeira rodada adicionou quatro
ofertas reais KaBuM; catálogo datado passou a seis produtos, seis imagens e seis
observações. As seis imagens carregaram efetivamente no Edge.

## Fontes e diagnóstico

| Fonte | Observação nesta etapa | Operação |
|---|---|---|
| KaBuM | Páginas públicas de produto com Product/Offer BRL em JSON-LD | Seis URLs explícitas; uma oferta por página; robots verificado |
| Mercado Livre | robots permite a listagem consultada, mas HTTP 302 aponta para `/gz/account-verification` | Desativado; redirecionamento não seguido |
| Pichau | robots permite a página consultada, mas servidor responde HTTP 403 | Desativado; sem retry ou contorno |

A resposta 403 não comprova a causa interna do bloqueio. Não foram usados CAPTCHA,
login, proxies, endpoints internos, cookies de outra sessão ou disfarce de navegador.
Os seletores HTML continuam sujeitos a alterações dos sites. Busca externa só foi
usada para localizar URLs públicas, nunca para importar preços em cache.

Alternativas oficiais verificadas:

- [KaBuM API/Mirakl](https://www.kabum.com.br/hotsite/documentacao-hubscore/):
  documentação de integração marketplace com credenciais de parceiro; não equivale
  a um feed anônimo autorizado de todo o varejo.
- [Afiliados KaBuM](https://www.kabum.com.br/hotsite/afiliados/): programa oficial;
  acesso a eventual feed/licença precisa ser confirmado após cadastro/autorização.
- [Pichau Creator Network](https://afiliados.pichau.com.br/): programa oficial com
  análise/aprovação de cadastro; nenhum feed anônimo de preços/imagens confirmado.
- [API Mercado Livre](https://developers.mercadolivre.com.br/pt_br/itens-e-buscas):
  referência oficial apresenta autenticação por token. A leitura direta da página
  de documentação retornou 403; escopos e acesso aos itens desejados ainda precisam
  ser validados por uma aplicação autorizada. Nenhum token ou endpoint privado usado.

Não foi confirmado feed público anônimo que resolva os dois bloqueios. Não se deve
supor que um cadastro de afiliado autoriza automaticamente coleta de todo o catálogo.

## Configuração

`config/collection_targets.json` contém apenas loja, URL pública e enabled. Alvos
atuais: KaBuM 112948, 98244, 621161, 955912, 356701 e 471957. As quatro primeiras
páginas ampliaram o catálogo; as duas últimas já tinham observações recentes e
foram puladas, respeitando o intervalo. Nenhum preço ou imagem foi inventado.

| Ambiente | Default | Limites |
|---|---|---|
| HUNTER_COLLECTION_ENABLED | 0 | 0/1; somente ativação explícita |
| HUNTER_COLLECTION_INTERVAL_SECONDS | 21600 | 21600..604800 (6h..7 dias) |
| HUNTER_COLLECTION_LIMIT | 6 | 1..6 páginas por rodada |
| HUNTER_COLLECTION_DELAY_SECONDS | 3 | 2..30 segundos entre tentativas |
| HUNTER_COLLECTION_TARGETS | config/collection_targets.json | JSON validado; até seis alvos ativos |

KaBuM exige URLs pontuais `/produto/ID/...`; hosts, HTTPS e ausência de credenciais,
query/fragmento são validados. IDs repetidos com slugs diferentes são deduplicados.
Não basta adicionar milhares de URLs: a configuração recusa mais de seis ativos.

Preferência local principal: `HUNTER_MAIN_COLLECTION_ENABLED=1` no arquivo ignorado
`.env.queue.local`, lida por `scripts/queue_environment.ps1`. No `-Test`,
HUNTER_COLLECTION_ENABLED é sempre 0. O carregador já impede trocar de teste para
principal no mesmo terminal. Nenhum segredo deve ser copiado para documentação.

Para desativar numa execução nova: definir HUNTER_COLLECTION_ENABLED=0 e reiniciar
somente o scheduler verificado. Configurações de intervalo/alvos são carregadas no
startup; reiniciar de forma coordenada para alterá-las. Não iniciar outro scheduler.

## Execução e consistência

- Mesmo processo `python -B -m messaging.scheduler`; uma tarefa assíncrona de coleta.
  Requests executa em thread; alertas/outbox mantêm seu ciclo durante o HTTP.
- A cada minuto o supervisor verifica trabalho devido. Nenhum HTTP ocorre quando
  cooldown/frescor do banco ainda impedem a coleta.
- Conexão PostgreSQL dedicada e advisory lock de sessão 281235 impedem coletores
  concorrentes no mesmo banco. Locks de scan/outbox existentes foram preservados.
- Estado `.env.collection-state.<hash-do-banco>.json`, ignorado pelo Git/Docker,
  registra execução, status, quantidades, próxima tentativa e bloqueios por loja.
  Escrito atomicamente antes do HTTP e ao finalizar. Não contém DSN ou credenciais.
- Antes de chamar a loja, o maior coletado_em já salvo da URL também é conferido.
  Reinício não recaptura uma URL recém-observada, mesmo se faltar estado local.
- A persistência existente é transacional, única por produto/data/fonte. Retorna
  quantidade realmente inserida; repetição exata não acrescenta observação. URLs
  repetidas na mesma rodada também são ignoradas.
- Preço igual em outra coleta legítima futura acrescenta observação datada, sem
  inventar variação. Scan continua notificando só novas transições relevantes.
- Falha HTTP/parse/banco não apaga nem substitui histórico. Falhas recebem backoff
  progressivo de até sete dias; 403/429/robots/desafio/redirecionamento suspendem a
  loja inteira por pelo menos 24h. Os outros alvos dessa loja não são tentados.
- Estado inválido falha fechado para a coleta; scan/outbox continuam operando.

Limite operacional: cooldown de falhas é local a este host. O lock PostgreSQL
impede concorrência entre instâncias, mas cooldown distribuído entre máquinas e
alta disponibilidade exigiriam estado compartilhado próprio em etapa futura.
Não remover o arquivo de estado para forçar tentativas. O computador e o scheduler
precisam permanecer ativos; inicialização automática do Windows não foi criada.

## Validação e observabilidade

`scripts/test_queue.ps1`: **64 testes**, demonstração RabbitMQ real isolada e
navegadores de catálogo/dashboard aprovados. Novos testes cobrem limites,
identidade, cooldown/restart, corrupção de estado, falhas, lock concorrente, HTTP
não bloqueante, histórico, consumo analítico e transições de alertas.

Logs do principal: `%TEMP%\HunterRuntime\scheduler.log`; inventário de PIDs em
`processes.json`. Linha de coleta contém loja, identificador do alvo, status,
produtos e imagens. Quantidade inserida e próxima execução ficam no estado local.
API, worker, frontend e RabbitMQ não foram reiniciados nesta etapa; somente o
scheduler recebeu o código/configuração novos.

Os endpoints `/analytics/*` já consomem as seis observações reais. Cada produto tem
uma observação: nenhuma queda/tendência é demonstrável e K-Means continua recusado.
A demonstração sintética permanece somente em memória. Confirmar a próxima rodada
após seis horas e acompanhar crescimento ao longo de dias; não encurtar o intervalo
para fabricar volume ou diversidade. Dados legados das três lojas foram preservados.
