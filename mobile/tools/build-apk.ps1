param([string]$ApiUrl = 'http://192.168.15.28:18089')
$ErrorActionPreference = 'Stop'
$mobileRoot = Split-Path $PSScriptRoot -Parent
$sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
if (!(Test-Path (Join-Path $sdk 'platform-tools\adb.exe'))) { throw 'Instale o SDK Android e configure ANDROID_HOME.' }
$names = 'ANDROID_HOME', 'ANDROID_SDK_ROOT', 'HUNTER_APK_PREVIEW', 'EXPO_PUBLIC_LOCAL_PREVIEW', 'EXPO_PUBLIC_API_URL', 'CI'
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
Push-Location $mobileRoot
try {
    $env:ANDROID_HOME = $sdk
    $env:ANDROID_SDK_ROOT = $sdk
    $env:HUNTER_APK_PREVIEW = '1'
    $env:EXPO_PUBLIC_LOCAL_PREVIEW = '1'
    $env:EXPO_PUBLIC_API_URL = $ApiUrl
    $env:CI = '1'
    # Apenas fontes Android geradas pelo Expo; elimina caches com o caminho anterior.
    npx expo prebuild --platform android --no-install --clean
    if ($LASTEXITCODE -ne 0) { throw 'Falha no prebuild.' }
    Push-Location android
    try {
        .\gradlew.bat assembleRelease --max-workers=2 '-PreactNativeArchitectures=arm64-v8a,x86_64' '-Dorg.gradle.jvmargs=-Xmx3072m -XX:MaxMetaspaceSize=768m'
        if ($LASTEXITCODE -ne 0) { throw 'Falha na compilacao Android.' }
    } finally { Pop-Location }
    New-Item -ItemType Directory -Force dist | Out-Null
    Copy-Item -LiteralPath 'android\app\build\outputs\apk\release\app-release.apk' -Destination 'dist\hunter-mobile-preview.apk' -Force
    Get-FileHash 'dist\hunter-mobile-preview.apk' -Algorithm SHA256
} finally {
    Pop-Location
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
