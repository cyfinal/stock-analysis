[CmdletBinding()]
param(
    [switch]$NoSyncLatest,
    [string]$SequoiaRoot = "C:\Users\Admin\Documents\Codex\2026-06-28\sequoia-x-daily",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $PSScriptRoot "sequoia-x"
}

$ReportsOut = Join-Path $OutputRoot "reports"
New-Item -ItemType Directory -Force -Path $ReportsOut | Out-Null

$Python = Join-Path $SequoiaRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "找不到 Sequoia-X Python 环境：$Python"
}

$SourceReports = Join-Path $SequoiaRoot "reports"

Push-Location $SequoiaRoot
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

    Write-Host ("同步完成：{0}" -f $LatestReport.BaseName)
    Write-Host ("日报：{0}" -f (Join-Path $ReportsOut $LatestReport.Name))
    Write-Host ("全量CSV：{0}" -f (Join-Path $ReportsOut (Split-Path -Leaf $CsvPath)))
    Write-Host ("最新日报快捷入口：{0}" -f (Join-Path $OutputRoot "LATEST.md"))
    Write-Host ("最新CSV快捷入口：{0}" -f (Join-Path $OutputRoot "latest_all_stocks_analysis.csv"))
}
finally {
    Pop-Location
}
