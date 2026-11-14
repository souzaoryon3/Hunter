# Contribuir com o Hunter

1. Use o snapshot sem historico ou clone apenas o novo repositorio autorizado.
   Configure sua stack e seus segredos com README.md. Nunca copie arquivos privados.
2. Depois de existir repositorio autorizado, crie branch por tarefa. Preserve
   compatibilidade HTTP, JWT, frontend, alertas, notificacoes e origem dos dados.
3. Separe rotas/schemas, regras de negocio e queries parametrizadas. Configuracoes
   devem vir do ambiente, sem paths absolutos ou senhas incorporadas.
4. Para mudancas de banco, crie nova migracao incremental e compativel, com lock,
   checksum e validacao em banco vazio e atualizado. Nao edite SQL aplicado.
5. Mantenha coleta externa desligada no desenvolvimento/testes. Respeite robots,
   licencas, quotas e bloqueios. Nao executar scrapers como efeito de imports.
6. Execute python scripts/dev.py test e o smoke dev quando alterar fluxo integrado.
   Verifique frontend desktop/mobile e estados vazios/erro ao alterar interface.
7. Revise o diff e o inventario de arquivos antes de propor commit. Nao inclua
   .env, .secrets, certificados, dumps, dados pessoais, logs ou tokens em fixtures.
   Exemplos devem ser ficticios e marcados; prefira example.invalid.
8. Atualize documentacao e CONTINUIDADE.md com mudancas, testes e limitacoes.
   Descreva no PR o problema, comportamento final e validacao. Commits, push,
   merges e publicacao dependem da autorizacao e do fluxo adotado pela equipe.

Para auditar a copia com Git: python scripts/audit_sharing.py --history. Relatorios
ficam ignorados em local-reports/ e nao contem valores detectados. O scanner e
heuristico: revise os achados e nao trate sua ausencia como prova completa.
Dados de teste nao devem ser apagados ou bancos limpos sem autorizacao.

Para regras criticas novas ou correcoes, registrar o ciclo TDD quando adotado:
especificar um teste observavel, executar e guardar a falha antes da mudanca,
implementar o minimo, executar novamente e refatorar mantendo os testes aprovados.
Separar esses passos em commits quando possivel. Testes escritos depois de uma
implementacao sao evidencia de regressao, sem apresenta-los como TDD retroativo.
Exemplo real e limites de comprovacao: docs/TDD_QUALIDADE.md.
