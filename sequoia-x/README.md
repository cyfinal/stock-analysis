# Sequoia-X 每日选股输出

这里是股票分析项目里的 Sequoia-X 接入目录。

## 文件说明

- `LATEST.md`：最新一次选股日报快捷入口。
- `latest_all_stocks_analysis.csv`：最新一次全市场股票分析快捷入口。
- `reports/YYYY-MM-DD.md`：按日期保存的选股日报。
- `reports/YYYY-MM-DD_all_stocks_analysis.csv`：按日期保存的全市场股票分析结果。

## 更新方式

在 PowerShell 中运行：

```powershell
cd E:\我的文档\股票分析
.\run_sequoia_x_daily.ps1
```

如果当天数据源或网络同步不稳定，但本地 Sequoia-X 数据库已经有可用数据，可以运行本地模式：

```powershell
cd E:\我的文档\股票分析
.\run_sequoia_x_daily.ps1 -NoSyncLatest
```

## 数据来源

脚本会调用：

`C:\Users\Admin\Documents\Codex\2026-06-28\sequoia-x-daily`

这个目录仍然是 Sequoia-X 策略代码、数据同步和测试的唯一维护位置。股票分析项目只接收生成后的日报和 CSV，避免两边策略逻辑不一致。

## 使用顺序

1. 运行 `run_sequoia_x_daily.ps1`。
2. 查看 `sequoia-x\LATEST.md` 获取每日策略 Top 结果和持有/减仓说明。
3. 查看 `sequoia-x\latest_all_stocks_analysis.csv` 获取全部 A 股分析结果。
