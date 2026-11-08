# Configuracao, segredos e privilegios — acoes explicitas

## Atualizacao: seguranca final aplicada em 07/11/2026

PostgreSQL/JWT/RabbitMQ principais foram rotacionados, roles minimas aplicadas,
cofres DPAPI separados e stack isolada em containers validada. Procedimentos,
recuperacao, evidencias e pendencias atuais: [SIMULACAO_PRODUCAO.md](SIMULACAO_PRODUCAO.md).
As secoes abaixo documentam a preparacao anterior; indicacoes de "NAO aplicado"
pertencem a essa etapa historica e foram superadas pelo provisionamento autorizado.

## Preparacao anterior ? o que foi corrigido

- DATABASE_URL obrigatoria; nenhum fallback com senha em codigo. Configuracao
  central em config/settings.py, sem carregar arquivos secretos no import.
- MIGRATION_DATABASE_URL separada, exclusiva das operacoes administrativas.
- URLs/configuracoes invalidas produzem mensagens sem revelar valores. DSNs nao
  aparecem no repr de Settings/APISettings.
- Producao exige TLS verify-full, AMQPS, CORS HTTPS explicito e segredo JWT forte;
  API/worker/scheduler recusam funcao administrativa no inicio, sem ALTER ROLE.
- JWT exige sub e exp; emissao continua HS256/60min e tokens legitimos permanecem
  compativeis. Hash e verificacao continuam fora do event loop.
- Guardas de integracao recusam principal, host remoto, porta/usuario/banco errado,
  parametros que tentem substituir o destino e terminais misturados. Todas as
  conexoes de teste sao validadas antes de conectar.
- .env.*, backups, caches e arquivos de recuperacao sao ignorados por Git/Docker.
  Ferramentas manuais que podem acessar principal foram retiradas de tests/.

## Exposicoes identificadas no HEAD Git (valores deliberadamente omitidos)

| Segredo | Local historico confirmado | Acao manual |
|---|---|---|
| Chave JWT literal | HEAD:auth.py:9 | Verificar reutilizacao e rotacionar nos ambientes afetados com planejamento de invalidacao de sessoes. |
| Credencial PostgreSQL | HEAD:scraping/buscar_produtoskabum.py:19 | Rotacionar a credencial exposta e substituir runtime por login de aplicacao dedicado. |
| Credencial PostgreSQL | HEAD:scraping/buscar_produtosmercadolivre.py:9 | Mesma revisao; pode representar a mesma credencial, nao assumir contas distintas. |
| Conexao padrao anterior da API | app.py anterior, preservado no recovery criptografado | Removida do codigo; conexao local anterior foi explicitada no arquivo ignorado, sem trocar senha. |

Nao foi reescrito o historico nem alterada qualquer senha. Esta verificacao nao
equivale a um scanner completo de todos os commits. Segredos locais de broker e
JWT ignorados nao foram considerados vazados sem evidencia, nem rotacionados
automaticamente. A funcao do principal continua a anterior e privilegiada; a
profissionalizacao nao deve ser apresentada como troca de privilegios concluida.

## Configuracao local e producao

O carregador Windows queue_environment.ps1 le explicitamente .env.runtime.local
para DATABASE_URL e opcional MIGRATION_DATABASE_URL, sem sobrescrever valores ja
exportados. Segredos JWT/broker anteriores continuam em .env.queue.local ignorado.
Esses arquivos sao locais em texto, nao um cofre de producao. Nao publicar, anexar
a relatorios, incluir em imagens nem compartilhar como exemplo. .env.example
contem apenas placeholders. Abra terminal novo para sair do ambiente de testes.

Na Azure, injetar configuracao por ambiente e cofre/identidade gerenciada aprovados;
nao montar o arquivo local com a credencial administrativa atual. Um segredo de
migracao nao deve ser fornecido ao container de runtime. O modo local permite a
funcao anterior para preservar funcionamento; habilitar producao exige preparar
as permissoes adequadas primeiro.

## Funcoes PostgreSQL — template NAO aplicado

ops/postgres_roles.sql prepara grupos NOLOGIN separados: hunter_runtime para DML
necessario e hunter_owner para DDL. Nao cria login com senha, nao executa
REASSIGN OWNED e nao e chamado por bootstrap ou migrador. Revisar manualmente:

1. Criar logins dedicados para aplicacao e migracao por canal administrativo seguro;
   definir credenciais fora de arquivos versionados.
2. Revisar propriedade de tabelas/sequencias/funcoes e associar o login migrador ao
   owner apropriado. GRANT comum nao substitui ownership necessario a ALTER TABLE.
3. Revisar grant de CONNECT/USAGE, ACL de PUBLIC e membership; o runtime nao deve
   herdar funcoes privilegiadas nem ser owner. Revisar novos grants a cada migracao.
4. Os gatilhos atuais de usuarios sao SECURITY INVOKER e escrevem em
   auditoria_usuarios: template inclui INSERT e uso da sequencia correspondente.
5. Validar CRUD, auditoria, historico, outbox e worker primeiro no isolado com os
   papeis dedicados. Somente entao, com autorizacao, trocar DSNs e rotacionar senha
   antiga em handoff planejado. Essa validacao de ACL ainda nao foi executada.

## Recuperacao e pendencias

Antes da primeira alteracao foi criado ZIP em memoria e protegido por DPAPI
CurrentUser, incluindo Git e arquivos nao rastreados, exceto ambiente virtual e
caches. Arquivo em %TEMP%/HunterRecovery/hunter_20261107_204959_8073d34d2fab4a50b312c3b86793e2dd.dpapi:
326 arquivos,3564566 bytes, descriptografia/contagem verificadas. Depende do mesmo
usuario Windows/contexto DPAPI. Restaurar primeiro em pasta nova, revisar e nunca
sobrescrever o projeto automaticamente. Copiar para armazenamento duravel protegido.
Originais do frontend tambem foram preservados em pasta de recovery separada.

Ainda pendentes: rotacao real de credenciais, aplicacao/teste das ACLs, limitacao
de login/analytics e politica CSP/scripts externos, estrategia de revogacao de
tokens, backup/restauracao de banco em armazenamento duravel, verificacao de
dependencias e retencao de auditoria. JWT em localStorage foi preservado para
nao mudar o contrato de autenticacao; requer protecao contra XSS e supply chain.
