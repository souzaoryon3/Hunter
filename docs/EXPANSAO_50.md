# Campanha de 50 novos produtos: criterios obrigatorios

Status em08/11/2026: **0/50 novos produtos concluidos**. Os seis IDs1?6 ja existentes
sao baseline e nao contam para a meta. Nao foram criados candidatos, precos,
observacoes ou metadados ficticios. Nenhuma migracao/coleta/reinicio foi executado.

## Cadastro aceito

Cada produto novo exige nome,marca,modelo,categoria,loja,URL HTTPS permitida da
oferta,preco positivo real,data UTC da coleta e observacao inicial vinculada ao
produto. Identidade e modelo devem vir de fonte verificavel, nunca deduzidos apenas
do nome. A imagem externa HTTPS deve corresponder ao modelo/variante correto,
com evidencia da mesma oferta e revisao de identidade. Nao armazenar binarios no
PostgreSQL. Se houver mais de uma imagem comprovada do modelo, pode-se validar
outra URL permitida; nunca trocar por imagem generica ou contornar bloqueios.

Na pagina de busca real do Hunter, a imagem deve estar complete,naturalWidth>0
e currentSrc igual a URL comprovada. Placeholder/fallback nao passa. Confirmar
nome,preco,loja e href,consultar historico e testar busca,filtros e comparacao.
A revisao semantica de marca/modelo/imagem e obrigatoria: uma imagem carregar
nao comprova que representa o produto correto. O preco nao pode vir de snippet
ou cache usado como se fosse captura atual.

Somente contar novos IDs e URLs distintos do baseline, com todas as evidencias.
Itens incompletos continuam pendentes e nao entram no total. Guardar observacao-ID,
URLs,instantes,resultado HTTP da coleta e evidencia de navegador. A prova de oferta
deve vir da rodada autorizada, sem abrir uma segunda coleta para verificar o link.

## Implementacao desta etapa

`catalog_expansion/qualification.py` fornece qualification_errors/campaign_summary,
sem HTTP,conexao,DML ou coleta em imports. Exige os campos e evidencias acima e
recusa produto antigo/duplicado,preco invalido,data anterior a campanha,historico
incompativel,fallback/imagem nao decodificada e integracao nao comprovada.

Este e um **contrato de aceite**, nao uma implementacao de coleta/comparacao nem
um certificado automatico de correspondencia visual. Evidencias devem ser produzidas
por coleta e revisao reais. Ainda nao foi integrado a persistencia do scheduler.
`config/expansion50.json` registra baseline/meta e lista vazia de ofertas permitidas;
nao altera config/collection_targets.json nem estado/quota das fontes.

## Bloqueios encontrados

- Apenas seis candidatos/paginas KaBuM existentes autorizados. Lista adicional/feed
  autorizado nao foi fornecido. Nao ha cinquenta novas URLs verificadas.
- Estado consultado somente leitura: fonte kabum_public enabled,limite6 produtos e
  12 reservas HTTP por janela de6h; seis candidatos,um active e cinco backoff.
  Prazo/quotas mantidos. Nao executar coletor paralelo ou reduzir cooldown.
- Cinquenta novos itens exigem no minimo nove rodadas com a capacidade atual:
  ao menos48h entre primeira e nona,sem contar candidatos antigos,falhas,backoffs
  ou indisponibilidade do computador. Isso nao e prazo garantido.
- Mercado Livre/Pichau permanecem sem acesso atual autorizado. Bloqueios anteriores
  nao foram testados novamente nem contornados.
- Marca/modelo/categoria nao existem como campos estruturados na persistencia/API
  atual; comparacao por identidade exata nao foi implementada. Antes de declarar
  os novos cadastros completos sera necessario integrar metadados,filtros e
  comparacao com migracao incremental segura,testes isolados e evidencia real.
- Alternativa documentada: [feeds oficiais Awin](https://www.awin.com/br/faq),
  condicionados ao acesso efetivo e permissoes do anunciante. Nenhuma conta,chave
  ou permissao foi presumida/criada.

## Validacao executada

- Seis testes de qualification: aprovados. Cobrem completude,baseline/duplicatas,
  imagem quebrada/fallback,modelo errado,historico/data e integracao/fonte.
- Ruff: aprovado. Sintaxe Python/JS e git diff --check conferidos nesta etapa.
- Edge na aplicacao principal,somente GET: seis imagens remotas reais decodificadas
  e hrefs correspondentes nos cards dos seis produtos preexistentes. Relatorio
  privado ignorado: local-reports/expansion50-baseline-images.json.
- Essa prova nao e nova coleta de preco/HTTP200 da oferta remota nem valida os
  novos campos estruturados. Portanto nenhum desses seis foi contado na meta.
- A regressao anterior de125 testes permanece historica desta expansao; nao foi
  apresentada como uma nova execucao integral. Nenhuma mudanca no runtime ocorreu.

Proximo insumo necessario: URLs pontuais adicionais de fonte permitida ou feed/API
ja autorizado para o Hunter,com identidade,preco e direitos de imagem verificaveis.
Nenhum commit,push,deploy,exclusao ou alteracao do banco principal nesta etapa.
