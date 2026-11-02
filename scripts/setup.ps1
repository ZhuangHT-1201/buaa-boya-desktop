# 一键安装依赖并初始化配置（密码稍后交互输入）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> 安装依赖..."
python -m pip install -r requirements.txt

# 确保 Scripts 在当前会话 PATH
$Scripts = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
if ($Scripts -and ($env:Path -notlike "*$Scripts*")) {
    $env:Path = "$Scripts;" + $env:Path
    Write-Host "已临时加入 PATH: $Scripts"
}

Write-Host "==> 初始化项目配置与 AutoBoya 数据目录"
python -m boya_kit init

Write-Host ""
Write-Host "接下来请运行（会提示输入学号和密码，密码只存本机钥匙串）："
Write-Host "  python -m boya_kit setup"
Write-Host "然后："
Write-Host "  python -m boya_kit refresh"
Write-Host "  python -m boya_kit status"
Write-Host "  python -m boya_kit preview"
Write-Host "  python -m boya_kit run-once   # 试跑一轮"
Write-Host "  python -m boya_kit run        # 后台常驻"
Write-Host ""
Write-Host "开机自启（可选）："
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\install-task.ps1"
