@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在准备博雅自动助手，首次运行需要安装依赖...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
if errorlevel 1 (
  echo.
  echo 启动失败，请查看上方错误信息。
  pause
)
