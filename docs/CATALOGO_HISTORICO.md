# Imagens e histórico de preços

Estado em 06/11/2026: migração 003 aplicada e conferida no principal hunter_db.
API/scheduler reiniciados; worker e RabbitMQ preservados. Amostra real KaBuM com
dois produtos, duas imagens externas verificadas no navegador e duas observações
(uma por produto). Mercado Livre redirecionou para fora da loja e Pichau respondeu
403; nenhum dado desses acessos foi importado. Resultados completos e backup em
CONTINUIDADE.md. O roteiro abaixo serve para outros ambientes/futuras instalações.

## Estrutura

Migração `003_catalogo_historico.sql`: duas tabelas novas, sem alterar/apagar as
tabelas antigas. `hunter_catalog_products` identifica a oferta por `(loja, link)`;
`hunter_price_observations` guarda nome, imagem HTTPS opcional, preços numeric(12,2),
pagamento, disponibilidade, frete, data real da observação, data de registro e fonte.
Não faz matching de SKU entre lojas. Não existe histórico reconstruído artificialmente.

A leitura escolhe a observação de maior `coletado_em`, com desempate pelo ID.
Importar uma captura antiga acrescenta histórico, sem reverter preço/imagem atuais.
Repetir a mesma observação é idempotente; conteúdo divergente na mesma identidade,
data e fonte é recusado. Lotes são transacionais. Uma observação mais recente de
indisponibilidade impede a volta da oferta legada da mesma loja/URL.

API e scheduler usam a mesma consulta. Não há alteração no protocolo das mensagens,
no worker ou na migração 002. Produtos legados continuam consultáveis durante a
transição, mas não entram no histórico novo sem uma coleta datada.
Mercado Livre legado escolhe o maior ID por URL, inclusive após mudança de nome;
KaBuM legado escolhe o maior ID por nome/URL porque o coletor antigo gravava URLs
de categoria para produtos distintos. IDs não comprovam data de coleta: esses preços
recebem `preco_verificado=false` e aviso na interface. Seus alertas continuam com a
semântica legada até receberem observações novas. Preço observado também pode
envelhecer: sempre exibir a data e confirmar condições na loja; não há TTL automático.

## API e interface

- `/buscar-produtos`: mantém campos anteriores e inclui `produto_id`, `imagem_url`,
  `preco_atual`, `preco_verificado` e `historico_disponivel`.
- `/produtos/{produto_id}/historico?pagina=1&limite=30`: histórico público, paginado,
  ordenado do mais recente ao mais antigo, com origem e datas. Limite máximo 100.
  Produto desconhecido: 404. Migração ausente: 503 sem quebrar a busca legada.
- Busca: imagem com fallback SVG local, carregamento lazy, sem Referer para a
  imagem externa, histórico expansível com paginação e indicação dos preços legados.

Correção em 07/11/2026: a busca ampla por teclado/mouse/monitor escondia as fotos
depois da primeira página porque preços legados baixos vinham antes dos observados.
`priorizar_observados=true` agora é o default da busca: catálogo observado primeiro,
com menor/maior preço dentro de cada grupo, antes da paginação. O controle
**Priorizar catálogo datado** permite desativar isso; `priorizar_observados=false`
ordena todos os registros globalmente por preço. Filtros e totais são preservados.
Essa prioridade é somente apresentação na busca; a detecção de alertas não mudou.

Validação principal somente leitura: com DATABASE_URL configurada, executar
`python -B scripts/manual/verify_search_images.py`. Exige seis produtos KaBuM observados no
principal; verifica as seis imagens por ID em buscas amplas, HTTP200/image/* e
decodificação no Edge, sem criar fixtures, alertas ou observações. A regressão
isolada inclui 30 legados mais baratos para reproduzir a falha de paginação.

## Procedimento para novas instalações — exige autorização

1. Confirmar novamente `current_database()`, porta e esquema do banco principal,
   comparar tabelas/índices com a 003 e atualizar o backup protegido.
2. Em terminal novo, configurar DATABASE_URL principal explicitamente, sem expor
   credenciais; não reutilizar terminal configurado com `-Test`.
3. Após autorização, executar:

   ```powershell
   .\.venv\Scripts\python.exe -B -m messaging.migrate --version 003
   ```

4. Conferir versão/checksum e reiniciar de maneira coordenada API e scheduler com
   o código novo, preservando configuração e broker. Worker/protocolo não mudaram.
5. Importar uma pequena captura autorizada com imagens e data original; verificar
   busca, histórico e alerta. Nenhuma imagem/histórico real aparece automaticamente
   só com a migração: é preciso coletar/importar observações válidas.

Não executar `messaging.testing` no principal. A suíte `.\scripts\test_queue.ps1`
aplica 002 e 003 somente no ambiente isolado. A 003 não é aplicada no startup.

## Coleta e Data Mining

Os três scrapers capturam imagem e observação datada; KaBuM e Mercado Livre passam
a gravar pela persistência comum, com DATABASE_URL obrigatória. KaBuM não executa
ao importar e passa a guardar o link real do produto. Pichau mantém seu upsert legado
e grava o histórico na mesma transação quando a 003 está disponível. Bloqueios
403/429 da Pichau continuam interrompendo a coleta, sem contorno.

Testes usam HTML sintético, sem coleta real. Seletores podem precisar de ajuste
quando os sites mudarem. URLs de imagens podem expirar ou negar hotlink; o fallback
é esperado. Não há download/proxy de imagens nem cache local de fotos nesta etapa.

Para amostras autorizadas existe `scripts/collect_sample.py`, com limite de 1 a 3
produtos, robots.txt e recusas sem retry de bloqueios. `--store` seleciona a loja;
`--url` aceita uma página HTTPS da mesma loja (exige uma única --store).
KaBuM agora aceita também Product/Offer BRL em JSON-LD da página pública do produto,
sem usar preços mínimos de AggregateOffer ou endpoints internos. As listagens
podem retornar HTML sem produtos: nesse caso nada é importado.
`scripts/manual/verify_main_catalog.py --allow-main-alert` é opt-in e adiciona um alerta ao
usuário sintético já existente; `--existing-alert 12` permite revalidar a fixture
desta entrega sem novas inserções. Exige ambiente principal explicitamente carregado.

A base temporal permite análise por produto/loja, variações, disponibilidade e
diferença entre coleta e ingestão. Ainda faltam volume temporal confiável,
normalização de identidade entre lojas e definição do modelo/indicador de Data Mining.
