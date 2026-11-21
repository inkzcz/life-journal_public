[CmdletBinding()]
param(
    [string]$Version,
    [string]$Revision,
    [string]$OutputDir,
    [string]$SourceRoot,
    [string]$SourceParent,
    [ValidateSet('auto','online','offline')][string]$Verification = 'auto',
    [switch]$Force,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
try {
    if ($PSVersionTable.PSVersion.Major -lt 5) { throw '需要 PowerShell 5 或更新版本。' }
    $Python = Get-Command py -ErrorAction SilentlyContinue
    $Prefix = @('-3')
    if (-not $Python) { $Python = Get-Command python -ErrorAction SilentlyContinue; $Prefix = @() }
    if (-not $Python) { throw '未找到 Python 3.10+。请安装 Python 并启用 launcher 或 PATH。' }
    & $Python.Source @Prefix -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
    if ($LASTEXITCODE -ne 0) { throw '需要 Python 3.10 或更新版本。' }
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONUTF8 = '1'
    $Arguments = $Prefix + @('-u', (Join-Path $PSScriptRoot 'release_local.py'), '--verification', $Verification)
    if ($Version) { $Arguments += @('--version', $Version) }
    if ($Revision) { $Arguments += @('--revision', $Revision) }
    if ($OutputDir) { $Arguments += @('--output-dir', $OutputDir) }
    if ($SourceRoot) { $Arguments += @('--source-root', $SourceRoot) }
    if ($SourceParent) { $Arguments += @('--source-parent', $SourceParent) }
    if ($Force) { $Arguments += '--force' }
    if ($VerifyOnly) { $Arguments += '--verify-only' }
    Write-Host 'Life Journal：自动读取版本，验证官方源码，仅构建本机 linux/amd64 镜像。'
    Write-Host '请先启动 Docker Desktop 并使用 Linux Containers；不会连接 NAS、删除镜像或推送 GHCR。'
    & $Python.Source @Arguments
    if ($LASTEXITCODE -ne 0) { throw "构建/校验失败（退出码 $LASTEXITCODE）。请保留上方日志，不要部署 partial 目录。" }
    Write-Host '交付成功。TAR 目录已在上方显示，请核对 SHA256SUMS.txt 和 manifest.json。'
    exit 0
} catch {
    Write-Host ('错误：' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
