[CmdletBinding()]
param(
    [switch]$Dev,
    [string]$BootstrapPython = ""
)

$ErrorActionPreference = "Stop"
$EngineRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $EngineRoot ".venv\Scripts\python.exe"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令失败，退出码 $LASTEXITCODE：$FilePath $($Arguments -join ' ')"
    }
}

function New-SequoiaVenv {
    param([string]$TargetVenv)

    if ($BootstrapPython) {
        if (-not (Test-Path -LiteralPath $BootstrapPython)) {
            throw "指定的 BootstrapPython 不存在：$BootstrapPython"
        }
        Invoke-CheckedCommand -FilePath $BootstrapPython -Arguments @("-m", "venv", $TargetVenv)
        return
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        Invoke-CheckedCommand -FilePath $py.Source -Arguments @("-3", "-m", "venv", $TargetVenv)
        return
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        Invoke-CheckedCommand -FilePath $python.Source -Arguments @("-m", "venv", $TargetVenv)
        return
    }

    throw "找不到 Python。请先安装 Python 3.10+，或用 -BootstrapPython 指定 python.exe。"
}

Push-Location $EngineRoot
try {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        New-SequoiaVenv -TargetVenv ".venv"
    }

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "虚拟环境创建失败，未找到：$VenvPython"
    }

    Invoke-CheckedCommand -FilePath $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    if ($Dev) {
        Invoke-CheckedCommand -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-e", ".[dev]")
    } else {
        Invoke-CheckedCommand -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-e", ".")
    }

    Write-Host "Sequoia-X 运行环境已准备好：$VenvPython"
}
finally {
    Pop-Location
}
