$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ReleaseExe = Join-Path $Root "release\博雅自动助手.exe"
$EnglishReleaseExe = Join-Path $Root "release\BoyaAutomation.exe"
if (Test-Path $ReleaseExe) {
    Start-Process -FilePath $ReleaseExe -WorkingDirectory (Split-Path -Parent $ReleaseExe)
    exit 0
}
if (Test-Path $EnglishReleaseExe) {
    Start-Process -FilePath $EnglishReleaseExe -WorkingDirectory (Split-Path -Parent $EnglishReleaseExe)
    exit 0
}

$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $Python) {
        throw "未找到 Python，且 release 目录中没有打包好的 EXE。"
    }
    Write-Host "==> 首次安装：创建独立运行环境..."
    & $Python.Source -m venv $Venv
}

Write-Host "==> 检查运行依赖..."
& $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt
Write-Host "==> 初始化本地配置..."
& $VenvPython -m boya_kit init

$Pythonw = Join-Path $Venv "Scripts\pythonw.exe"
if (-not (Test-Path $Pythonw)) {
    $Pythonw = $VenvPython
}
Start-Process -FilePath $Pythonw -ArgumentList @("-m", "boya_kit.launcher") -WorkingDirectory $Root
