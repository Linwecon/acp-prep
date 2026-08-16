# ACP 备考助手 - 一键更新部署脚本
# 由 一键更新.bat 调用；也可右键"使用 PowerShell 运行"
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   ACP 备考助手 - 一键更新部署" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] 配置网络代理..."
git config http.proxy http://127.0.0.1:7897
git config https.proxy http://127.0.0.1:7897

Write-Host "[2/3] 提交变更..."
git add -A
git commit -m "update $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>$null | Out-Null

Write-Host "[3/3] 推送到 GitHub..."
git push

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "   更新成功！约 1-2 分钟后线上自动生效" -ForegroundColor Green
    Write-Host "   大家访问的链接将自动更新，无需其他操作" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "   推送失败！请按顺序排查：" -ForegroundColor Red
    Write-Host "   1. 确认代理软件（Clash 等）已开启运行" -ForegroundColor Red
    Write-Host "   2. 若代理端口不是 7897，请修改本文件" -ForegroundColor Red
    Write-Host "      第 11/12 行中的端口号后重试" -ForegroundColor Red
    Write-Host "   3. 确认网络正常后重新双击 一键更新.bat" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
}
Write-Host ""
Read-Host "按回车键退出"
