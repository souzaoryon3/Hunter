# Data Mining e dashboard do Hunter

Implementado sem migracao nova. O modulo consulta a estrutura da 003 somente com
SELECT e nao altera precos, alertas, notificacoes ou eventos do RabbitMQ.

## Uso

Abra `http://127.0.0.1:5500/dashboard.html` ou o link **Analises** da navegacao.
Origem inicial: dados reais. A opcao de demonstracao usa nove produtos ficticios,
72 observacoes e lojas identificadas como ficticias; os registros sao gerados em
memoria e nunca inseridos no PostgreSQL. Trocar de origem limpa resultados anteriores.

Endpoints publicos (dados de catalogo, sem informacoes pessoais):

| GET | Parametros | Resultado |
|---|---|---|
| `/analytics/estatisticas` | origem=real/demo, dias=1..365 (90), produto_id opcional, limiar=1..90 (5) | resumo, estatisticas e sinais por produto |
| `/analytics/historico/{produto_id}` | origem, dias | serie temporal, media movel e estatisticas do produto |
| `/analytics/agrupamentos` | origem, dias, k=2..5 (3) | grupos ou mensagem explicita de dados insuficientes |

Migração 003 ausente: 503. Produto inexistente na origem escolhida: 404.
Parametros invalidos: 422. Mais de 20.000 observacoes na consulta: 413; reduza o
periodo ou selecione um produto. Nao ha amostragem/truncamento silencioso.

## Dados e estatistica (Pandas)

`repository.py` usa SQL parametrizado sobre `hunter_catalog_products` e
`hunter_price_observations`, nunca sobre precos legados sem data. As fontes reais
permitidas sao `html_publico`, `http_publico`, `html_publico_jsonld` e
`captura_publica`. Fontes de fixtures/demo/desconhecidas ficam fora da origem real.
Uma fonte nova legitima precisa ser incluida explicitamente nessa lista.

`analysis.py` descarta precos nao finitos/nao positivos, datas invalidas/futuras e
ordena cronologicamente. Mesmo produto/instante conta uma unica vez, com desempate
pelo maior ID de observacao. As janelas sao relativas ao horario UTC da consulta;
dias distintos sao contados em UTC. O dashboard mostra horarios no fuso do navegador.

Calculos por oferta (loja + URL, sem misturar produtos diferentes):

- Media aritmetica, minimo, maximo e quantidade de observacoes validas do periodo.
- Variacao percentual = `(ultimo / primeiro - 1) * 100`.
- Queda recente = `(1 - ultimo / penultimo) * 100` (positivo indica queda).
- Desconto sobre media anterior = `(1 - ultimo / media_sem_ultima) * 100`.
- Volatilidade = `desvio_padrao_populacional / media * 100`.
- Media movel simples de tres observacoes; as duas primeiras nao recebem valor.
  Nao ha imputacao de datas nem de precos entre coletas; a linha liga pontos observados.

Com uma observacao: media/minimo/maximo sao o unico preco conhecido; variacao,
queda e volatilidade ficam nulas. Nao se infere estabilidade ou tendencia.
As medias sao por observacao, nao ponderadas pelo tempo nem por vendas.

## Quedas e oportunidades

Queda detectada: pelo menos duas observacoes, queda >= limiar (5% por padrao),
ultima oferta disponivel, ultima coleta em ate sete dias e intervalo entre as duas
ultimas coletas de no maximo sete dias.

Oportunidade exige tambem pelo menos tres observacoes em dois dias UTC distintos
e desconto >= limiar sobre a media anterior. Sao regras descritivas e exploratorias,
sem garantia de oferta vigente, menor preco de mercado ou retorno financeiro.
Estoques, frete e equivalencia de SKU entre lojas nao sao inferidos.

## K-Means (scikit-learn)

Uma linha por produto elegivel: disponivel, ultima coleta em ate sete dias, pelo
menos tres observacoes validas em dois dias UTC distintos. Para k grupos exigimos:

- Pelo menos `max(6, 2*k)` produtos elegiveis.
- Pelo menos k+1 vetores numericos distintos e duas caracteristicas variaveis.

Caracteristicas: `log1p(preco_medio)`, volatilidade percentual, variacao percentual
e quantidade de observacoes. A transformacao log reduz o efeito de escalas de preco
muito diferentes. [StandardScaler](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html)
centraliza e padroniza as colunas antes do
[KMeans](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html),
com `random_state=42`, `n_init=10` e limite de threads na etapa numerica.

Se os criterios falham, K-Means nao e executado: status `dados_insuficientes`, sem
grupos inventados. Numeros dos grupos sao ordenados pela media apenas para exibir
de maneira consistente; nao sao notas de qualidade. Nao ha previsao, classificacao
de SKUs equivalentes, escolha automatica de k ou validacao preditiva nesta entrega.
O agrupamento e calculado sob demanda, sem modelo persistido nem jobs em background.

## Arquitetura e validacao

- `analysis.py`: funcoes de Pandas e agrupamento independentes do banco.
- `repository.py`: leitura limitada/parametrizada.
- `demo.py`: dataset ficticio separado e somente em memoria.
- `api.py`: rotas; calculos em threadpool para nao bloquear o event loop da API.
- `dashboard.html` / `dashboard.js`: SVG local responsivo, tabelas acessiveis,
  indicadores, filtros, carregamento, vazio, insuficiencia, erros e recuperacao.

Dependencia nova: `scikit-learn==1.5.2`; Pandas/Numpy ja estavam instalados. Instalar
requirements no ambiente Python 3.12 antes de iniciar uma nova instancia da API.

Em terminal de teste: `. .\scripts\queue_environment.ps1 -Test` e
`.\scripts\test_queue.ps1`. Inclui **53 testes** (42 anteriores + 11 de mineracao),
demo RabbitMQ com dois workers, regressao do catalogo/frontend e teste do dashboard.
Para somente a tela: `python -B tests/browser_dashboard.py` (Edge, portas 8003/5503).
Processos temporarios do teste sao encerrados ao terminar.

No principal em 06/11/2026: dois produtos reais e duas observacoes, sem quedas ou
oportunidades demonstraveis. K-Means recusado corretamente, zero produtos elegiveis.
O dashboard local foi habilitado reiniciando apenas API/frontend; nenhum registro
novo foi gravado, nenhuma migracao aplicada. Contagens conferidas antes/depois.

Proximos passos: coletas pequenas autorizadas ao longo do tempo, mais produtos e
fontes permitidas, avaliacao de qualidade/viés de amostragem e validacao dos sinais
antes de qualquer uso como recomendacao. Cache e processamento em lotes devem ser
avaliados quando o volume real justificar. Mercado Livre/Pichau continuam limitados
por acesso; esta etapa nao tentou coletar produtos.
