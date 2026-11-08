param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$BuildVenv = Join-Path $Root ".build-venv"
$Python = Join-Path $BuildVenv "Scripts\python.exe"
$ExeName = "博雅自动助手"
$Icon = Join-Path $Root "assets\boya.ico"
$VersionInfo = Join-Path $Root "assets\version_info.txt"
$ExampleConfig = Join-Path $Root "config.example.yaml"
$Launcher = Join-Path $Root "boya_kit\launcher.py"
$ReleaseDir = Join-Path $Root "release"
$WorkDir = Join-Path $Root "build\pyinstaller"
$SpecDir = Join-Path $Root "build"
if (-not (Test-Path $Python)) {
    $SystemPython = Get-Command python -ErrorAction Stop
    Write-Host "==> 创建打包环境..."
    & $SystemPython.Source -m venv $BuildVenv
}

if (-not $SkipInstall) {
    Write-Host "==> 安装打包依赖..."
    & $Python -m pip install --disable-pip-version-check -q -r requirements-build.txt
}

Write-Host "==> 生成应用图标..."
& $Python scripts\create_icon.py

$PyInstaller = Join-Path $BuildVenv "Scripts\pyinstaller.exe"
if (-not (Test-Path $PyInstaller)) {
    throw "未找到 PyInstaller，请重新运行本脚本并允许安装依赖。"
}

Write-Host "==> 构建单文件 EXE..."
& $PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $ExeName `
    --icon $Icon `
    --version-file $VersionInfo `
    --add-data "$ExampleConfig;." `
    --add-data "$Icon;assets" `
    --collect-all autoboya `
    --collect-all keyring `
    --collect-data ddddocr `
    --hidden-import "keyring.backends.Windows" `
    --hidden-import "ddddocr" `
    --distpath $ReleaseDir `
    --workpath $WorkDir `
    --specpath $SpecDir `
    $Launcher

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 构建失败。"
}

$ChineseExe = Join-Path $ReleaseDir "$ExeName.exe"
$EnglishExe = Join-Path $ReleaseDir "BoyaAutomation.exe"
Copy-Item -LiteralPath $ChineseExe -Destination $EnglishExe -Force

Write-Host ""
Write-Host "构建完成：$EnglishExe"
