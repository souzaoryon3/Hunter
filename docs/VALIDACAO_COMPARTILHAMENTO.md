# Validacao de compartilhamento ? 08/11/2026

Resultado: **APTO pelo snapshot sem historico + pacote PostgreSQL cifrado e
anonimizado separado**. O .git original NAO e apto para publicacao. Nenhuma
publicacao, commit, push, reescrita, deploy ou envio executado.

## Evidencias

- Stack limpa hunter-dev: PostgreSQL vazio, baseline/001?005, broker novo, seis
  processos/servicos saudaveis, frontend/API/worker/scheduler, sem segredos locais
  anteriores. Oferta ficticia identificada permite o smoke sem dados reais.
- Regressao Linux em hunter-team-test: **125 testes, nenhum skip, cobertura81%**,
  Ruff e testes reais de ACK/retry/DLQ/idempotencia aprovados. Chromium passou
  fluxo completo, desktop/mobile, CRUD/autenticacao, notificacoes e dashboard
  real/demo com Pandas/K-Means. Bibliotecas/navegador instalados em imagem nova.
- Host Windows/Docker Desktop: smoke dev aprovado e teste Edge real na restauracao.
  Sintaxe Python de100 modulos, JavaScript e git diff --check aprovados.
- Quatro testes adicionais verificam integridade canonica, chave errada sem
  iniciar Docker, guard de instancia e restauracao transacional sem limpar schema.

## Dados efetivamente transferidos e restaurados

Pacote final: hunter-database-20261108T105746058746Z.enc, criado de snapshot
consistente somente leitura da origem. AES-256-GCM; dump custom PostgreSQL16.
Manifesto autenticado e SHA256 acompanham o procedimento. Emails e hashes de
senha da origem nao aparecem no SQL sanitizado. Anonimizacao so na copia.

| Conteudo | Quantidade no ponto transferido |
|---|---:|
| Tabelas public preservadas |22|
| Produtos do catalogo datado |6|
| Observacoes de preco datadas |13|
| Candidatos / execucoes de coleta |6 /6|
| Alertas / notificacoes |6 /5|
| Usuarios com IDs preservados e identidades anonimizadas |5|
| Auditoria anonimizada / feedback anonimizado |79 /3|
| Catalogo legado KaBuM / Mercado Livre / Pichau |3008 /1411 /6|
| Tabela legada produtos_backup |1440|

Todas as22 contagens foram comparadas antes/depois da sanitizacao e no restore
final. Hashes de todas as linhas dos catalogos (incluindo produtos_backup),
observacoes, candidatos e migracoes identicos. Schema, sequences, funcoes e triggers
restaurados sem roles/ownership/permissoes antigas. Alteracoes de privacidade
preservam IDs/FKs; conteudo pessoal e senhas originais nao sao reproduzidos.

A aplicacao restaurada passou: seis produtos com precos/imagens correspondentes
na busca,13 observacoes no historico, **seis imagens externas decodificadas** no
Edge, login de identidade preservada com senha nova, cadastro/login novo, alerta,
scheduler/publisher/RabbitMQ/worker, notificacao e leitura persistida, estatisticas
reais, agrupamentos demo e dashboard mobile. Teste acrescentou fixtures somente
na copia restaurada; arquivo cifrado permanece com as contagens do snapshot.

## Limites e arquivos

A auditoria Git encontrou tres blobs historicos com segredos antigos; foram
preservados no original e excluidos pelo snapshot sem .git. Achados atuais sao
placeholders/interpolacao/fixtures/marcador de senha desativada, revisados sem
imprimir valores. Scanner e heuristico; nao e certificacao absoluta.

O ZIP lista cada arquivo em SHARE_MANIFEST.json e tem checksum externo. Inclui
codigo, frontend/imagens locais, testes, migracoes, Docker, configuracoes-modelo e
documentacao. Ignora .env privados,cofres/chaves/certificados,backups/dumps,dados
locais,logs,caches,.git e volumes. Inventarios privados ficam em local-reports/.

Imagens/Google Fonts/VLibras dependem da internet; o backup conserva URLs, nao a
licenca/bytes de imagens de lojas. Todas as seis imagens carregaram neste teste,
sem garantir disponibilidade futura. O broker novo comeca sem mensagens antigas;
outbox/historico de notificacoes ficam no PostgreSQL. Coletores ficam desligados.
Agrupamentos reais podem legitimamente retornar dados insuficientes.

Nao foi testada execucao remota de GitHub Actions nem uma segunda maquina fisica:
o destino foi reproduzido em novos containers Linux no Docker Desktop Windows,
com banco/broker/segredos separados e restore do pacote final. Requisitos e passos
para o colega estao em README.md e TRANSFERENCIA_WINDOWS.md.
