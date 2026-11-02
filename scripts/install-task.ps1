# 注册 Windows 计划任务：登录后自动启动 boya_kit 后台循环
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$TaskName = "BUAA-BoyaKit"
$Python = (Get-Command python).Source
$Args = "-m boya_kit run"

# 若已有任务先删除
schtasks /Query /TN $TaskName 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    schtasks /Delete /TN $TaskName /F | Out-Null
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument $Args -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal | Out-Null
Write-Host "已注册计划任务: $TaskName"
Write-Host "立即启动一次:"
Write-Host "  schtasks /Run /TN $TaskName"
Write-Host "卸载:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-task.ps1"
