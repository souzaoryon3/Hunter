# Hunter Mobile

Aplicativo **nativo Android e iOS**, em React Native 0.88.1, Expo SDK 58 e TypeScript.
Branch inicial: `feat/app-mobile-react-native`, criada a partir de
`feat/coleta-multiloja-scrapling-stealth` / `7cdd71e`.

## O que está implementado

- Ofertas reais da API, categorias de busca, filtro de loja/preço/frete, ordenação,
  paginação, atualização por gesto e tratamento de conexão indisponível.
- Detalhe da oferta, imagens com fallback, condições de pagamento, link HTTPS da
  loja e histórico paginado de observações.
- Cadastro/login da conta Hunter. JWT no armazenamento seguro nativo
  (`expo-secure-store`), restauração de sessão e tratamento de expiração.
- Criação, edição e exclusão confirmada de alertas, com o preço desejado e a
  menor oferta atual devolvida pelo backend.
- Notificações da conta com paginação e marcação de leitura; edição do perfil e
  rotação do JWT devolvido pela API.
- Configuração de conexão dentro de **Conta → Conexão**. A troca de servidor
  encerra a sessão anterior, sem reutilizar seu token no novo endereço.

O app consome a **mesma API FastAPI**, que acessa o **mesmo PostgreSQL**.
Nenhuma credencial do banco fica no app. Não há banco paralelo, migração nova ou
importação duplicada de produtos. Contas e alterações são compartilhadas com a web.

## Preparar

Use Node.js 24 ou superior, npm e a stack Hunter em execução. Não é necessário
ter Android Studio para testar com Expo Go em um celular.

Na raiz do projeto, a stack existente desta máquina usa:

```powershell
.venv\Scripts\python.exe -B scripts/dev.py status --instance scrapling
```

A API está atrás de `http://127.0.0.1:18088`. Para uma instalação nova, use o
procedimento do README principal e ajuste as portas abaixo conforme a instância.

```powershell
cd mobile
npm ci
npm start
```

Instale o **Expo Go compatível com SDK 58** e leia o QR do Metro. A versão do Expo
Go pode ser conferida em [expo.dev/go](https://expo.dev/go).

## Conectar ao banco existente pela API

### Emulador Android

O padrão em desenvolvimento é `http://10.0.2.2:18088`, que aponta para o loopback
do computador. Inicie o emulador e execute `npm run android`.

### Celular Android ou iPhone na mesma rede Wi-Fi

A stack de desenvolvimento publica portas apenas no loopback. Para o celular,
use a ponte de API abaixo, sem expor PostgreSQL, RabbitMQ, arquivos locais ou
ferramentas administrativas.

Terminal 1, na raiz do projeto; substitua `IP_DO_PC` pelo IPv4 da rede local:

```powershell
python scripts/mobile_api.py --host IP_DO_PC --port 18089
```

Terminal 2:

```powershell
cd mobile
$env:EXPO_PUBLIC_API_URL = 'http://IP_DO_PC:18089'
npm start -- --lan
```

O celular precisa alcançar as portas 8081 (Metro) e 18089 (ponte). Se o sistema
pedir acesso à rede local para Expo Go ou Python, permita-o na rede de
desenvolvimento. Não é preciso abrir portas do banco nem alterar autenticação.

Também é possível copiar `.env.example` para `.env.local` e configurar
`EXPO_PUBLIC_API_URL`, ou informar a URL diretamente em **Conta → Conexão**.
O arquivo `.env.local` é ignorado pelo Git. Use a ponte HTTP somente no ambiente
local de desenvolvimento; builds de distribuição exigem uma API HTTPS.

### Android físico por USB

Com Android Platform Tools instalado e depuração USB habilitada:

```powershell
adb reverse tcp:18088 tcp:18088
adb reverse tcp:8081 tcp:8081
```

Configure a API do app como `http://127.0.0.1:18088`. Nesse modo a ponte Wi-Fi não
é necessária. No simulador iOS no próprio Mac, use `http://127.0.0.1:18088` se o
backend estiver nesse Mac; caso esteja em outro computador, use a ponte pela rede.

## Verificar

```powershell
npm run lint
npm run check
npx expo-doctor
npm run export:native
npm audit
```

`check` executa TypeScript estrito e testes do cliente HTTP, autenticação,
cancelamento de busca, erros, filtros, dinheiro em BRL e links externos.
`export:native` gera bundles Hermes **Android e iOS** em `dist/` (ignorado pelo Git).
Esses bundles não são APK/IPA nem substituem testes em um aparelho.

Para validar os contratos de leitura contra a API real, sem criar usuários ou
alterar dados:

```powershell
npm run test:api -- http://127.0.0.1:18088
```

Os testes Python da ponte também integram a suíte existente:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_mobile_bridge.py -v
```

Os ícones do Hunter são vetores locais; `npm run assets` regenera os PNGs.
O override de `minimatch` no fingerprint do Expo corrige o advisory
GHSA-g3hv-75wg-m249 sem rebaixar o SDK. O fingerprint e os bundles foram
validados com essa versão.

## APK Android de teste

No Windows, com Java e SDK Android instalados:

```powershell
powershell -ExecutionPolicy Bypass -File tools/build-apk.ps1 -ApiUrl http://192.168.15.28:18089
```

O script gera `dist/hunter-mobile-preview.apk`, com JavaScript incluido e assinatura
de teste local. Nao depende do Expo Go ou do Metro. Instale o APK no Android e
mantenha o celular na mesma rede da API. A URL pode ser alterada na tela Conexao.
Esse build aceita HTTP somente para IPs privados/loopback; HTTPS tambem funciona.
As flags `HUNTER_APK_PREVIEW=1` e `EXPO_PUBLIC_LOCAL_PREVIEW=1` sao exclusivas
desse modo. Sem elas, builds de distribuicao exigem HTTPS.
O plugin `plugins/withShortCmakePaths.js` limita caminhos de objetos CMake a 240
caracteres e usa o cache curto `~/.hcx/` para evitar MAX_PATH no Windows.
O script regenera somente o Android
gerado pelo Expo e restaura as variaveis ao terminar.
Nao coloque alteracoes manuais em `android/`; use a configuracao Expo/plugins.
Pastas nativas e APK
permanecem ignorados pelo Git. A chave de teste nao serve para publicar nas lojas.

## Builds nativos e limitações

Para um build local Android, instale Android Studio/SDK e Java compatível com o
SDK Expo, depois use `npx expo run:android`. Para iOS, use macOS com Xcode e
`npx expo run:ios`. As pastas geradas `android/` e `ios/` são ignoradas.
Builds de distribuição devem receber `EXPO_PUBLIC_API_URL` com HTTPS antes de
gerar o bundle. Valores `EXPO_PUBLIC_*` são públicos; nunca use senhas ou JWTs ali.

As notificações desta versão são **dentro do app**, lidas da API ao abrir a aba
ou atualizar. Push do sistema, modo offline com sincronização, assinatura de
producao/IPA e publicação nas lojas não estão configurados. Os filtros não inventam ofertas para
lojas sem dados. Os testes automatizados não substituem a validação visual e de
teclado/acessibilidade em Android/iOS físico.
