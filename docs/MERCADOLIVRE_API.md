# Mercado Livre oficial: preparacao minima e ponto de autorizacao

Estado: cliente preparado,SEM aplicativo/token/OAuth configurados eSEM novas
capturas reais. Nenhum acesso a terceiros foi confirmado para o Hunter.
O ultimo teste real de /sites/MLB/search?q=teclado&limit=5,sem token,retornou403;
essa resposta nao demonstra o resultado de uma chamada autenticada.

## Recursos e limites

| Endpoint | O que fornece | Limite importante |
|---|---|---|
| GET /sites/MLB/search?q=TERMO | Busca de anuncios sem filtro seller_id | Documentada; acesso efetivo deste app/MLB depende de OAuth e politicas. Nao prometer busca global so por possuir token. |
| GET /users/SELLER_ID/items/search | IDs de anuncios de UM vendedor | Nao e descoberta global; conta/permissoes e escopos se aplicam. |
| GET /products/search?site_id=MLB&status=active&q=TERMO | Modelos do catalogo,nomes e imagens | Nao prova que existe oferta compravel/preco atual. |
| GET /products/CATALOG_ID | Modelo e buy_box_winner quando exposto | Vencedor pode ser de outro seller; nao e lista completa de vendedores. |
| GET /items/ITEM_ID | Titulo,seller_id,pictures,permalink,status/estoque | Campos privados podem ser omitidos; price legado nao e a fonte escolhida. |
| GET /items/ITEM_ID/sale_price?context=channel_marketplace | Preco vigente no contexto solicitado | Metadata promocional e limitada para token que nao pertence ao vendedor. Falha nao autoriza usar preco antigo. |

A alternativa oficial preparada e catalog search -> produto -> anuncio vencedor
visivel -> item -> sale_price. Modelo sem vencedor visivel e ignorado. Nao ha
fallback automatico ao receber401/403/429: resolver autorizacao,nao testar rotas
como forma de contornar uma recusa. Os modos sao escolhas explicitas.

## Finalidade e aprovacao

Os termos do Programa limitam finalidade,copia,armazenamento,redistribuicao e usos
concorrentes. Nao foi encontrada uma dispensa academica especifica. **OAuth nao
substitui a permissao de uso do conteudo para comparacao/historico.** Antes de
coletar,pedir confirmacao ao suporte do Programa de Desenvolvedores para a
finalidade exata do Hunter e para anuncios de sellers diferentes. Nao afirmar
que o Hunter e ERP ou representante de vendedores que nao autorizaram o projeto.
A ausencia de necessidade de certificacao DPP para operacao propria nao concede
permissoes de catalogo irrestritas a um comparador.

Texto para a consulta pelo titular da conta:

> O Hunter e um projeto academico de comparacao de ofertas de eletronicos,com
> exibicao de imagens,links e historico de precos. Precisamos descobrir anuncios
> de vendedores distintos no MLB. Este uso e autorizado? Quais recursos,scopes,
> regras de retencao/exibicao e eventual aprovacao devem ser utilizados?

## Sua etapa no navegador (parar aqui antes do OAuth)

1. Abra o [guia oficial de criacao](https://developers.mercadolivre.com.br/pt_br/realizacao-de-testes/crie-uma-aplicacao-no-mercado-livre),
   clique em DevCenter/Minhas aplicacoes e entre com a conta titular do projeto.
   Se ja existe app adequado,abra suas configuracoes; nao crie duplicado nem
   renove/exclua credenciais existentes. O portal pode exigir validacao de identidade.
2. Para app novo,clique Criar uma aplicacao. Sugestao de nome: Hunter Academico;
   nome curto: hunter-academico (se disponivel). Descricao transparente:
   "Projeto academico Hunter: comparacao de ofertas e historico de precos de eletronicos,com links para anuncios do Mercado Livre."
   Preencha dados/logo solicitados com informacoes verdadeiras do projeto.
3. Unidade de negocio: Mercado Livre/MLB,nao Mercado Pago. Permissoes minimas:
   Usuarios e Publicacao e sincronizacao,**somente leitura**,para items/pictures/prices.
   Nao pedir escrita,vendas,mensagens ou publicidade. Para o primeiro teste,nao
   precisamos de offline_access; refresh automatico ainda nao foi implementado.
4. Em Autenticacao e seguranca,preferir Authorization Code e PKCE S256. A URI de
   redirect deve ser HTTPS,estatica,exatamente igual no app e na troca do code,
   sob seu controle. **Nao use endereco de exemplo/de terceiros nem callback que
   registre codes em logs.** Se voce nao tem callback HTTPS proprio,pare nessa
   tela e informe essa limitacao: precisamos preparar o retorno seguro antes de
   salvar/autorizar. Nao presuma que o portal aceita localhost/HTTP.
5. Sem webhook para este teste: nao ativar topicos de notificacao que nao usaremos.
   Se algum campo impedir continuar,informar apenas o nome do campo e a mensagem,
   sem credenciais. Nao inventar URL de notificacao.
6. Apos criacao/configuracao aprovada,guardar Client ID e Client Secret apenas
   localmente. Informar ao assistente somente o Client ID (publico),a URI de
   retorno escolhida e as permissoes disponiveis. **Nao colar Client Secret,
   code,Access Token ou Refresh Token na conversa.**

O proximo passo,apos isso,e preparar state/PKCE,autorizar no dominio oficial
https://auth.mercadolivre.com.br/authorization e trocar o code no backend em
POST https://api.mercadolibre.com/oauth/token. Nao iniciar manualmente uma URL sem
state nem enviar o code a servico de terceiros. Esta etapa NAO foi executada.

## Cliente preparado e configuracao

O coletor existente scraping/buscar_produtosmercadolivre.py ganhou o modo --api.
Credenciais por ambiente,com nomes documentados em .env.example. A API nao le
.env automaticamente: exportar no shell ou usar um carregador local protegido.
Client Secret nao e usado para GET; o Bearer Access Token e necessario. Nenhum
segredo real foi criado,alterado ou salvo nesta preparacao.

Somente depois das autorizacoes e token configurado:

```text
python -B scraping/buscar_produtosmercadolivre.py --api --mode general --query teclado --limit 5
# Alternativa de catalogo,se houver acesso permitido a esse recurso:
python -B scraping/buscar_produtosmercadolivre.py --api --mode catalog --query ssd --limit 5
```

Sem --persist,nao escreve no banco. Para gravar,carregar DATABASE_URL do ambiente
correto e acrescentar --persist --expect-database NOME_EXATO. Usa save_observations,
lock de coleta e CandidateRepository existentes. A nova fonte fica disabled ate
validacao real e configuracao do monitoramento; nenhum scheduler/adaptador foi
ativado. O historico identifica api_oficial_mercadolivre,sem tokens na URL.

Comecar por ate5 ofertas,varrendo termos diferentes; depois validar imagens reais,
links,busca/filtros e historico no frontend antes de ampliar para25. O cliente faz
apenas GET,sem seguir redirects,com3s entre chamadas e sem retry de bloqueios.
Recusa oferta estrangeira,inativa,sem estoque/imagem HTTPS ou variantes ambiguas.
Nao importa preco antigo de /items nem valor de catalogo sem anuncio verificavel.

## Fontes oficiais consultadas

- [Busca/itens](https://developers.mercadolivre.com.br/pt_br/itens-e-buscas)
- [Busca geral e paginacao](https://developers.mercadolivre.com.br/pt_br/busca-produtos-por-categoria/consideracoes-de-design)
- [Busca de modelos](https://developers.mercadolivre.com.br/pt_br/produto-consulta-de-usuarios/buscador-de-produtos)
- [Vencedor de catalogo](https://developers.mercadolivre.com.br/pt_br/produto-consulta-de-usuarios/concorrencia-em-catalogo)
- [Precos e acesso de terceiros](https://developers.mercadolivre.com.br/devcenter/api-de-precos)
- [Permissoes funcionais](https://developers.mercadolivre.com.br/pt_br/produto-consulta-de-usuarios/permissoes-funcionais)
- [OAuth/PKCE](https://developers.mercadolivre.com.br/pt_br/autenticacao-e-autorizacao)
- [Validacao da conta](https://developers.mercadolivre.com.br/devcenter/validacoes-de-dados)
- [Termos do Programa](https://developers.mercadolivre.com.br/pt_br/termos-e-condicoes)

Algumas aberturas diretas da documentacao retornaram403 nesta ferramenta; foram
consultados os conteudos oficiais indexados. Nao houve contorno desses bloqueios.
