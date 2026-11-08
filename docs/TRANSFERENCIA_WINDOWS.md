# Transferencia integral para outro desenvolvedor ? Windows, VS Code e Docker

## O que e transferido

Sao **dois pacotes separados**: snapshot do projeto sem .git (ou futuro clone do
novo repositorio autorizado) e pacote PostgreSQL `hunter-database-*.enc`. A chave
`transfer-*.key` e um terceiro item privado: nunca incluir no Git nem enviar junto
com o arquivo cifrado. Nenhum arquivo foi enviado a outra pessoa por esta preparacao.

O pacote de dados usa AES-256-GCM, chave aleatoria de 256 bits e nonce aleatorio;
a autenticacao detecta chave errada/adulteracao antes de iniciar o destino. Contem
dump custom PostgreSQL16 (schema public, todas as tabelas/sequences/funcoes/triggers)
e manifesto com contagens, hashes de catalogo/historico/candidatos e hash do dump.
Nao inclui roles, senhas de conexao, JWT ou mensagens/credenciais do broker original.
Produtos reais, precos legados, imagens por URL, observacoes datadas, candidatos,
fontes, alertas, estados, eventos e notificacoes permanecem por ID e relacionamento.

A copia e **anonimizada para desenvolvimento**, nao uma copia de identidades reais:
usuarios ficam como Integrante transferido ID, email transfer-ID@example.invalid,
senhas antigas invalidadas; feedback e auditoria de usuarios recebem placeholders.
Emails/nomes de usuarios sao retirados de campos funcionais de alertas/eventos
quando encontrados. Payloads ficam restritos aos campos usados pela mensageria.
O heartbeat e marcado parado, sem PID do computador original. Nenhuma linha e
apagada: contagens de todas as tabelas sao comparadas. Catalogo, historico e
candidatos devem conservar hashes identicos. Emails/hashes de senha de origem sao
comparados contra o SQL sanitizado e impedem exportacao se encontrados.

Dados de interesses de compra e IDs vinculados permanecem: trate o pacote como
restrito a equipe, mesmo anonimizado. Conteudo pessoal original nao e necessario
para reproduzir o sistema e nao esta no pacote. O banco principal nao e alterado.

## Preparar uma nova copia no computador do operador

Somente se realmente precisar atualizar o ponto de transferencia:

```powershell
.venv\Scripts\python.exe scripts/transfer_database.py prepare-operator
```

Este comando requer cliente PostgreSQL16 (pg_dump no PATH ou instalacao padrao),
asyncpg e cryptography, Docker iniciado e acesso ao cofre DPAPI administrativo ja
existente do operador. Nao pede nem altera sua senha. Le a origem hunter_db:5432
com default_transaction_read_only=on e snapshot repeatable-read compartilhado com
pg_dump. O dump bruto fica em memoria e e restaurado em container novo, sem portas
e sem volumes principais. Somente essa copia recebe anonimiza??o. O container
final de staging fica **parado e preservado**, nao deve ser transferido. Tentativas
interrompidas tambem ficam locais; nao usar seus arquivos/volumes como pacote.

A saida informa caminhos, nunca valores: local-data/transfers/*.enc, manifesto
local .json e .secrets/transfer-*.key. Arquivos sao novos; nada anterior e apagado.
A chave tem acesso local restrito pelo diretorio privado .secrets. No Linux novos
arquivos de chave recebem modo600. Nao mover chave para pasta publica/sincronizada.

## Transportar com seguranca (somente apos autorizacao)

1. Conferir os caminhos finais indicados na entrega e SHA256 do pacote.
2. Enviar somente o .enc por um canal privado com acesso ao integrante correto.
3. Entregar a chave correspondente por **outro canal autenticado**, preferencialmente
   cofre corporativo com compartilhamento individual e expiracao. Confirmar a
   identidade do destinatario; nao registrar chave em issue/PR/chat publico/log.
4. Nao enviar cofres DPAPI, .env locais, certificados, dumps antigos, .git original,
   credenciais de PostgreSQL/RabbitMQ/JWT ou backups pessoais. Eles nao sao necessarios.
5. Se algum futuro conector exigir chave de API/licenca, criar credencial propria
   para o integrante ou aprovar acesso pelo gestor. Nada disso e indispensavel ao
   funcionamento local atual, com coleta externa desligada.

Nao existe comando de envio automatico. Esta etapa fica aguardando autorizacao.

## Instalar e restaurar em Windows

Instale Git, VS Code, Python3.12 e Docker Desktop/WSL2 com containers Linux e
Compose2.24+. Abra a pasta do snapshot/clone no VS Code. No terminal PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Credenciais inteiramente suas; use portas livres:
py -3.12 scripts/dev.py configure --instance equipe --http-port 8098 --management-port 15698
```

Guarde o pacote em `local-data/transfers/` e a chave correspondente em `.secrets/`
(ambas ignoradas; crie as pastas se necessario). **Nao execute up antes do restore**:
isso inicializaria o banco de demonstra??o e o restore recusaria o destino ocupado.

```powershell
.venv\Scripts\python.exe scripts/transfer_database.py restore --package local-data/transfers/hunter-database-SEU_PACOTE.enc --key-file .secrets/transfer-SUA_CHAVE.key --instance equipe
py -3.12 scripts/dev.py up --instance equipe
py -3.12 scripts/dev.py status --instance equipe
```

O restore descriptografa em memoria, verifica hash e sobe somente PostgreSQL e
RabbitMQ novos. Recusa destino com qualquer tabela public; nao usa --clean, DROP,
TRUNCATE ou restauracao sobre banco existente. Aplica o dump em transacao unica,
sem ownership/grants antigos. O schema public ja existe no PostgreSQL novo: apenas
a criacao redundante dele e omitida do TOC; todos os outros erros interrompem.
Compara todas as contagens e hashes antes de permitir a continuidade. Se falhar,
nao apague nada: escolha outra instancia NOVA e investigue o erro.

Ao iniciar a aplicacao, o bootstrap somente confere as migracoes; **nao injeta a
oferta ficticia no banco restaurado**. O modo de demonstracao de Data Mining continua
em memoria. Acesse http://localhost:8098 e API http://localhost:8098/docs. O broker
fica em http://localhost:15698, usuario hunter_dev, senha propria no arquivo local
.env.dev.equipe.local. Nao exponha estas portas alem de loopback.

Cadastre uma conta nova para desenvolver. Para inspecionar os alertas/notificacoes
de um ID antigo preservado, ative **somente a identidade anonimizada na sua copia**:

```powershell
.venv\Scripts\python.exe scripts/transfer_database.py activate-user --instance equipe --user-id 1
```

A senha nova e solicitada sem eco e gravada com bcrypt. Login passa a ser
transfer-1@example.invalid. O comando recusa contas que nao estejam no estado de
transferencia desativada e nao possui conexao com a origem. Nao se usam senhas/JWT
originais. Cadastros existentes no principal nunca sao modificados.

Para parar/retomar sem perder dados:

```powershell
py -3.12 scripts/dev.py stop --instance equipe
py -3.12 scripts/dev.py up --instance equipe
```

O modo Linux usa os mesmos comandos com python3.12 e os executaveis da venv em
.venv/bin/. Certificados do operador nao sao necessarios. Para testes novos e
independentes, siga README: dev.py test-configure, test e test-stop.

## Disponibilidade e dependencias externas

O backup preserva **URLs de imagens**, nao transfere os bytes/licencas das imagens
das lojas. Imagens dependem de internet, CDN, URL valida e permissao da fonte;
podem expirar ou retornar403 no outro computador. O frontend possui fallback
local. Nao se deve prometer imagens remotas offline nem copiar arquivos de lojas
sem direito de redistribuicao. Links de compra/precos atuais tambem dependem das
lojas. Google Fonts e VLibras dependem de acesso externo; a aplicacao principal
continua operando sem esses recursos auxiliares.

RabbitMQ comeca vazio, com credenciais novas. O PostgreSQL preserva outbox e logs;
scheduler republica eventos pendentes/retry e published vencidos pela recuperacao
(normalmente300s), com idempotencia. Eventos processed/cancelled/dead e notificacoes
continuam historicos: nao se cria copia dos corpos das filas, DLQ ou ACKs antigos.
Nunca compartilhar volume vivo do broker entre computadores. Testes reais de
ACK/retry/DLQ/duplicidade validam o broker novo separadamente.

Coleta externa fica desligada, fontes/candidatos e seus prazos sao preservados.
Ativar coleta em outro computador requer revisar permissoes, quotas e locks por
banco: duas copias independentes nao compartilham lock/quota e poderiam duplicar
acessos. Nao ativar automaticamente. Sem API/afiliado/licenca nova nesta entrega.
Data Mining real depende de datas/quantidade/diversidade; restaurar o banco nao
cria dados novos nem garante agrupamentos quando ha amostra insuficiente.
