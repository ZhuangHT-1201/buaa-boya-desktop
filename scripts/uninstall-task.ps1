$ErrorActionPreference = "Stop"
$TaskName = "BUAA-BoyaKit"
schtasks /Delete /TN $TaskName /F
Write-Host "已卸载计划任务: $TaskName"

# 同时请求停止正在运行的循环
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python -m boya_kit stop 2>$null
