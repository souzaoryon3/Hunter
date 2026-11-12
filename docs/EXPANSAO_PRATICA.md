# Expansao pratica — verificacao de 07/11/2026

Resultado: **zero produtos e zero candidatos novos**. Catalogo datado permanece
com seis produtos KaBuM, seis imagens e12 observacoes. Uma loja operacional para
coleta atual; registros legados de outras lojas nao equivalem a ofertas atuais.

## Descoberta e limites conferidos

- Lidos continuidade, rotacao, adaptadores e fila persistente; Git consultado e
  alteracoes anteriores preservadas.
- PostgreSQL principal consultado somente leitura. Fonte kabum_public enabled,
  seis candidatos, quota usada6 produtos/12 reservas HTTP na janela iniciada em
  07/11/2026 22:17:50 UTC. Nenhum prazo, quota ou estado foi alterado.
- Proxima elegibilidade de rodada08/11/2026 04:17:26 UTC (~01:17:26 Sao Paulo),
  sujeita a janela da fonte ate04:17:50 UTC e supervisor; inicio pode ser~01:18 ou
  depois. Nao houve coleta manual, antecipacao de janela nem scheduler --once.
- Os3008 registros legados KaBuM nao contêm links https://www.kabum.com.br/produto/;
  portanto nao fornecem paginas pontuais novas para o adaptador atual. Nomes e
  precos legados nao foram convertidos em novas ofertas.
- Capturas locais existentes kabum-product-sample.html e kabum-sample.html foram
  analisadas offline: nenhum link adicional /produto/ nos anchors; dados Next.js
  nao forneceram objetos de produtos adicionais verificaveis. Nenhuma captura
  antiga foi reimportada como observacao atual.
- Busca publica encontrou categorias/listagens indexadas, mas nao novas URLs
  pontuais com identidade/preco/imagem individualmente verificaveis pelos canais
  consultados. Snippets/listagens em cache nao foram usados como preco atual.
- A consulta de https://www.kabum.com.br/devemos ignorar o robots.txt pela ferramenta web retornou
  HTTP403. Isso nao comprova que o coletor local esteja bloqueado: sua fonte
  permanece habilitada e nao foi modificada com base nesse resultado externo.
  Nao foi tentada outra rota/UA/browser para contornar o403. Quota local esgotada
  tambem impede validacao direta adicional fora da rotacao nesta janela.
- Sem evidencia suficiente para admitir novos candidatos como verificados, nao
  foram cadastradas categorias, URLs inferidas, produtos ou precos ficticios.

## Segunda loja: fontes oficiais verificadas

- [KaBuM afiliados](https://www.kabum.com.br/hotsite/afiliados/) confirma ingresso
  via Awin, sujeito a cadastro/aprovacao. O
  [perfil oficial Awin17729](https://ui.awin.com/merchant-profile/17729?setLocale=en_GB)
  confirma o programa; nao confirma que o Hunter ja possui acesso ao feed.
- [Awin: feeds](https://help.awin.com/developers/docs/product-feed-publisher-guide-intro)
  documenta nomes, precos, imagens e links para comparadores, com lista limitada
  aos feeds acessiveis a conta. E via viavel para varejo, condicionada a aprovacao
  do anunciante, disponibilidade efetiva e direitos de retencao/analise. Nenhuma
  chave, login ou conta foi criada/usada nesta investigacao.
- [Terabyte: regulamento oficial](https://www.terabyteshop.com.br/site/regras-programa-de-parceiros)
  confirma programa proprio sujeito a aprovacao, mas a secao8,item7 proibe
  recursos automatizados para extrair informacoes/materiais. Programa de parceiros
  nao autoriza um coletor do Hunter. Exigiria permissao expressa distinta e fonte
  autorizada; nenhum conector ativado. Esta evidencia complementa o diagnostico
  anterior, que ainda nao havia confirmado o programa em fonte oficial.
- [Magalu: materiais oficiais](https://www.parceiromagalu.com.br/divulgador/venda-mais/post/saiba-como-utilizar-as-imagens-de-produtos-em-suas-redes-sociais.html)
  descreve uso de imagens disponibilizadas aos participantes para divulgacao;
  [termos](https://www.magazinevoce.com.br/termos-de-uso/) exigem autorizacao para
  imagens/expressoes da marca. Nao comprovam API/feed de varejo autorizado para
  comparador, armazenamento historico e Data Mining. B2B nao foi usado como varejo.
- Nenhuma segunda loja com acesso efetivamente autorizado para o Hunter foi
  confirmada. Nao foi ativada nova fonte nem presumida permissao a partir de
  cadastro de afiliado ou de documentacao publica.

## Validacao e proximo passo concreto

Executado exclusivamente no ambiente isolado:

```powershell
. .\scripts\queue_environment.ps1 -Test
$env:PYTHONPATH='tests'
.venv\Scripts\python.exe -B -m unittest test_catalog test_catalog_candidates test_rotation -q
```

**48 testes aprovados, sem skips**: catalogo/imagens/historico/alertas, candidatos,
concorrencia, leases, quotas, rotacao e fontes nao autorizadas. Ultima regressao
total continua100 testes da Etapa2; nao se trata de nova execucao dos100 nesta
investigacao. Sem modificacao de codigo, migracao, configuracao ou servicos.

Para destravar: obter lista de URLs pontuais revisadas com permissao de coleta,
ou feed de varejo efetivamente habilitado para conta aprovada, incluindo direitos
de imagem e retencao. Depois admitir candidatos sem mudar o proximo horario e
validar ofertas na janela normal, no maximo seis por rodada. Nao executar
coletor paralelo para preencher24 produtos imediatamente.
