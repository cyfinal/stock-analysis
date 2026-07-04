[CmdletBinding()]
param(
    [switch]$NoSyncLatest,
    [string]$EngineRoot = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $EngineRoot) {
    $EngineRoot = Join-Path $PSScriptRoot "sequoia-x-engine"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $PSScriptRoot "sequoia-x"
}

if (-not (Test-Path -LiteralPath $EngineRoot)) {
    throw "找不到 Sequoia-X 引擎目录：$EngineRoot"
}

$Python = Join-Path $EngineRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "找不到 Sequoia-X Python 环境：$Python。请先运行：.\sequoia-x-engine\setup_env.ps1"
}

$ReportsOut = Join-Path $OutputRoot "reports"
New-Item -ItemType Directory -Force -Path $ReportsOut | Out-Null
$SourceReports = Join-Path $EngineRoot "reports"

Push-Location $EngineRoot
try {
    $ReportArgs = @("scripts\codex_daily_report.py", "--backfill-if-empty")
    if ($NoSyncLatest) {
        $ReportArgs += "--no-sync-latest"
    }

    & $Python @ReportArgs
    if ($LASTEXITCODE -ne 0) {
        throw "日报生成失败，退出码：$LASTEXITCODE"
    }

    $LatestReport = Get-ChildItem -LiteralPath $SourceReports -Filter "20??-??-??.md" |
        Sort-Object BaseName -Descending |
        Select-Object -First 1

    if (-not $LatestReport) {
        throw "没有找到 Sequoia-X 日报文件：$SourceReports\20??-??-??.md"
    }

    & $Python "scripts\export_all_stocks_analysis.py" "--from-report" $LatestReport.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "全量股票 CSV 导出失败，退出码：$LASTEXITCODE"
    }

    $CsvPath = Join-Path $LatestReport.DirectoryName ("{0}_all_stocks_analysis.csv" -f $LatestReport.BaseName)
    if (-not (Test-Path -LiteralPath $CsvPath)) {
        throw "没有找到全量股票 CSV：$CsvPath"
    }

    Copy-Item -LiteralPath $LatestReport.FullName -Destination (Join-Path $ReportsOut $LatestReport.Name) -Force
    Copy-Item -LiteralPath $CsvPath -Destination (Join-Path $ReportsOut (Split-Path -Leaf $CsvPath)) -Force
    Copy-Item -LiteralPath $LatestReport.FullName -Destination (Join-Path $OutputRoot "LATEST.md") -Force
    Copy-Item -LiteralPath $CsvPath -Destination (Join-Path $OutputRoot "latest_all_stocks_analysis.csv") -Force

    $WebUpdateScript = Join-Path $PSScriptRoot "scripts\update_sequoia_web_results.py"
    if (Test-Path -LiteralPath $WebUpdateScript) {
        & $Python $WebUpdateScript `
            "--report" (Join-Path $OutputRoot "LATEST.md") `
            "--csv" (Join-Path $OutputRoot "latest_all_stocks_analysis.csv") `
            "--output" (Join-Path $PSScriptRoot "daily-stock\sequoia-daily-results.js")
        if ($LASTEXITCODE -ne 0) {
            throw "网页结果数据更新失败，退出码：$LASTEXITCODE"
        }
    }

    Write-Host ("同步完成：{0}" -f $LatestReport.BaseName)
    Write-Host ("日报：{0}" -f (Join-Path $ReportsOut $LatestReport.Name))
    Write-Host ("全量CSV：{0}" -f (Join-Path $ReportsOut (Split-Path -Leaf $CsvPath)))
    Write-Host ("最新日报快捷入口：{0}" -f (Join-Path $OutputRoot "LATEST.md"))
    Write-Host ("最新CSV快捷入口：{0}" -f (Join-Path $OutputRoot "latest_all_stocks_analysis.csv"))
    Write-Host ("网页结果数据：{0}" -f (Join-Path $PSScriptRoot "daily-stock\sequoia-daily-results.js"))
}
finally {
    Pop-Location
}
