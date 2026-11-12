$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$android = Join-Path $PSScriptRoot "android"
$jdk = "C:\Android\jdk-17"
$gradle = "C:\Android\gradle-8.7"
$keystore = Join-Path $PSScriptRoot "android.keystore"
$work = "C:\Android\build\monetka"
$alias = "monetka"
$storePass = "monetka-store"
$keyPass = "monetka-store"

$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = "C:\Android\sdk"
$env:ANDROID_SDK_ROOT = "C:\Android\sdk"
$env:PATH = "$jdk\bin;C:\Android\sdk\platform-tools;$env:PATH"

$keytool = Join-Path $jdk "bin\keytool.exe"
if (-not (Test-Path $keystore)) {
    Write-Host "Creating signing key..."
    & $keytool -genkeypair -v -keystore $keystore -alias $alias -keyalg RSA -keysize 2048 `
        -validity 10000 -storepass $storePass -keypass $keyPass `
        -dname "CN=Monetka, OU=Mobile, O=Monetka, L=Moscow, C=RU"
    if ($LASTEXITCODE -ne 0) { throw "keytool failed" }
}

$line = (& $keytool -list -v -keystore $keystore -alias $alias -storepass $storePass) |
    Select-String -Pattern "SHA256:" | Select-Object -First 1
if (-not $line) { throw "SHA256 not found in keytool output" }
$sha = ($line.ToString() -replace ".*SHA256:\s*", "").Trim().Replace(":", "").ToUpper()
Write-Host "SHA-256: $sha"

# UTF-8 reading and writing explicitly: Windows PowerShell reads BOM-less UTF-8 as ANSI.
$utf8 = New-Object System.Text.UTF8Encoding($false)
$stringsPath = Join-Path $android "app\src\main\res\values\strings.xml"
$strings = [System.IO.File]::ReadAllText($stringsPath, $utf8)
if ($strings -match "__SHA256__") {
    [System.IO.File]::WriteAllText($stringsPath, ($strings -replace "__SHA256__", $sha), $utf8)
    Write-Host "Fingerprint written to strings.xml"
} else {
    Write-Host "strings.xml already has a fingerprint"
}

Write-Host "Writing assetlinks.json..."
& python (Join-Path $PSScriptRoot "make_assetlinks.py") $sha
if ($LASTEXITCODE -ne 0) { throw "assetlinks failed" }

# Gradle refuses non-ASCII project paths, so build from an ASCII copy.
Write-Host "Copying project to $work ..."
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force (Split-Path $work) | Out-Null
Copy-Item $android $work -Recurse -Force
Set-Content -Path (Join-Path $work "local.properties") -Value "sdk.dir=C\:\\Android\\sdk" -Encoding ASCII

Write-Host "Building APK..."
Push-Location $work
try {
    $env:MONETKA_KEYSTORE = $keystore
    $env:MONETKA_STORE_PASSWORD = $storePass
    $env:MONETKA_KEY_ALIAS = $alias
    $env:MONETKA_KEY_PASSWORD = $keyPass
    & (Join-Path $gradle "bin\gradle.bat") assembleRelease --no-daemon
    if ($LASTEXITCODE -ne 0) { throw "gradle build failed" }
} finally {
    Pop-Location
}

$built = Join-Path $work "app\build\outputs\apk\release\app-release.apk"
if (-not (Test-Path $built)) { throw "APK not found" }
$apk = Join-Path $PSScriptRoot "monetka-1.0.0.apk"
Copy-Item $built $apk -Force
Write-Host "APK: $apk"
Write-Host "Install: adb install -r `"$apk`""
