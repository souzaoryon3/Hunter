# Regras de trabalho — Hunter

Estas regras se aplicam a todo o projeto.

1. Antes de modificar arquivos, leia `CONTINUIDADE.md` e verifique o estado do Git.
2. Preserve as funcionalidades existentes do backend FastAPI, frontend, PostgreSQL e autenticação JWT.
3. Trabalhe autonomamente nas tarefas autorizadas, incluindo implementação, testes e correções.
4. Execute os testes adequados após cada alteração e relate falhas que não conseguir resolver.
5. Nunca apague dados existentes do PostgreSQL sem autorização explícita.
6. Nunca execute operações destrutivas no banco sem autorização.
7. Não faça commit, push, reset ou descarte alterações existentes sem autorização.
8. Nunca exponha credenciais, senhas, tokens ou segredos nos arquivos versionados ou relatórios.
9. Antes de alterar estruturas do banco, avalie a compatibilidade e crie migrações seguras.
10. Ao concluir uma tarefa, atualize `CONTINUIDADE.md` com implementações, testes, limitações e pendências.
11. Informe os arquivos modificados e os resultados dos testes.
12. Instrucoes explicitas do usuario sobre o escopo prevalecem sobre escolhas de implementacao. Se a tarefa permitir modificar somente arquivos especificos, respeite esse limite, inclusive quanto a atualizacao de `CONTINUIDADE.md`.
