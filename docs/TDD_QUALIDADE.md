# Evidencias de qualidade CI e TDD

## Escopo comprovado de TDD

Em 14/11/2026 foi executado um ciclo novo e real de TDD para uma correcao do
classificador de titulos: um kit que contem mouse e mousepad deve reconhecer
ambos. A regra anterior removia mouse sempre que encontrava mousepad, apagando
um item legitimo do combo. Nao foi alterado o comportamento para mousepad isolado.

Os passos foram executados nessa ordem e preservados em commits separados:

1. RED, commit 8e328d1: teste novo antes da correcao; falhou com AssertionError
   nos dois exemplos. Evidencia real em evidence/tdd-combo/red.json.
2. GREEN, commit 1286f53: correcao minima para distinguir mouse independente
   de mouse seguido de pad. Mesmo teste aprovado, sem mudar a especificacao.
   Evidencia em evidence/tdd-combo/green.json.
3. REFACTOR, commit c04b52d: extracao de matching_categories para separar regra
   tematica de limpeza/montagem; teste continuou aprovado. Evidencia em
   evidence/tdd-combo/refactor.json.

Cada registro inclui horario UTC, comando, resultado, HEAD anterior e SHA256
do teste e da implementacao. O hash do teste e igual nas tres fases. A captura
foi feita por scripts/tdd_evidence.py, que executa o teste existente, nao muda o
codigo e recusa sobrescrever evidencias. RED nao e falha atual: representa o
estado anterior a correcao. Os commits foram criados localmente na ordem acima
e publicados juntos com HEAD aprovado, sem disparar deliberadamente CI quebrada.

Esse caso comprova uma pratica concreta de TDD. Nao comprova que todo o projeto
ou as implementacoes anteriores tenham sido desenvolvidos por TDD. A sequencia
inicial de testes de PLN tambem ocorreu antes do modulo, mas nao tinha registro
versionado separado suficiente para sustentar uma afirmacao sobre o projeto todo.

## Testes e cobertura

A suite roda em PostgreSQL e RabbitMQ isolados, com guards contra o banco da
aplicacao e coleta externa desligada. Inclui testes unitarios/integracao e demos
com processos reais, ACK, retry, DLQ, idempotencia, streaming e PLN. Navegador
verifica login, CRUD, busca, dashboard e autocomplete em desktop/celular.

Coverage mede linhas dos pacotes Python configurados em pyproject.toml e exige
80%. Nao mede cobertura total de frontend/mobile nem precisao estatistica de PLN.
A ultima entrega anterior tinha 217 testes e 83%; o novo teste TDD aumenta a
quantidade para 218, sujeita ao resultado da execucao registrada de CI.

## Integracao continua

.github/workflows/ci.yml executa jobs validate e mobile em push na main e PRs
para main. validate testa backend/banco/broker, cobertura, navegador e builds.
mobile verifica TypeScript, testes do cliente e bundles Android/iOS, sem prometer
validacao em aparelhos fisicos. Comandos com tee preservam pipefail para que a
gravacao de log nao transforme falha de teste em sucesso.

Artefatos de cada execucao preservam logs unitarios, cobertura textual/XML/JSON,
resumo com commit/run, demos, capturas isoladas e registros TDD. Retencao: 30 dias.
Somente caminhos explicitamente permitidos sao enviados; nenhum .env, dump,
credencial, arquivo de login da demo ou inventario completo do ambiente e enviado.
Senhas efemeras geradas no runner sao mascaradas. Os registros TDD versionados
continuam disponiveis apos expirar o artefato.

Para comprovar a CI, apresentar a URL da execucao, SHA do commit, conclusao dos
dois jobs e o artefato hunter-quality. O status do workflow nao significa que
regras de protecao da main estejam habilitadas; essa configuracao e independente.
O resultado remoto sera registrado apos a execucao efetiva, sem atribuir ao
GitHub um resultado obtido somente no computador local.

Arquivos desta etapa: teste e correcao/refatoracao em tests/test_nlp.py e
nlp/analysis.py; scripts/tdd_evidence.py, scripts/ci_summary.py,
scripts/ci_environment.py, .github/workflows/ci.yml, docs/evidence/tdd-combo,
este documento e registros de continuidade/publicacao. Demais arquivos publicados
pertencem as entregas anteriores de streaming e PLN, ja validadas localmente.
