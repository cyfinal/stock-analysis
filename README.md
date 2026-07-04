# 股票分析

这个仓库保存股票研究报告、Sequoia-X 每日选股策略引擎，以及每日选股输出。

## 目录

- `sequoia-x-engine/`：完整 Sequoia-X 选股策略引擎，包含策略代码、数据引擎、日报脚本、全市场导出脚本、回测脚本和测试。
- `sequoia-x/`：最新日报和全市场股票分析结果的快捷输出目录。
- `run_sequoia_x_daily.ps1`：从本仓库内部运行 Sequoia-X，并同步最新结果到 `sequoia-x/`。
- `optical-module-report-page/`：光模块报告网页发布版。
- `中国光模块产业投资策略_2026-06-13.html`：光模块产业投资策略报告。
- `中国光模块产业与龙头投资策略_深度版_2026-06-13.html`：光模块产业深度版报告。

## 首次准备 Sequoia-X 环境

在 PowerShell 中运行：

```powershell
cd E:\我的文档\股票分析
.\sequoia-x-engine\setup_env.ps1 -Dev
```

`-Dev` 会同时安装测试依赖，便于后续验证。日常只运行策略时可以不带 `-Dev`。

## 更新每日选股输出

```powershell
cd E:\我的文档\股票分析
.\run_sequoia_x_daily.ps1
```

如果数据源同步不稳定，但本地数据库已经有可用数据，可以使用本地模式：

```powershell
.\run_sequoia_x_daily.ps1 -NoSyncLatest
```

输出位置：

- `sequoia-x\LATEST.md`：最新选股日报。
- `sequoia-x\latest_all_stocks_analysis.csv`：最新全市场股票分析。
- `sequoia-x\reports\YYYY-MM-DD.md`：按日期保存的日报。
- `sequoia-x\reports\YYYY-MM-DD_all_stocks_analysis.csv`：按日期保存的全市场 CSV。

## GitHub 提交规则

本仓库不提交：

- `sequoia-x-engine\.venv\`
- `sequoia-x-engine\data\*.db`
- `.ssh` 私钥
- 嵌套 `.git` 元数据
- Python 缓存目录

本地数据库 `sequoia-x-engine\data\sequoia_v2.db` 会保留在电脑上，用于离线和快速生成报告，但不会上传到 GitHub。
