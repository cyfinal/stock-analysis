# 股票分析

这个目录保存股票研究报告和 Sequoia-X 每日选股输出。

## 目录

- `中国光模块产业投资策略_2026-06-13.html`：光模块产业投资策略报告。
- `中国光模块产业与龙头投资策略_深度版_2026-06-13.html`：光模块产业深度版报告。
- `optical-module-report/`：光模块报告网页版本。
- `sequoia-x/`：Sequoia-X 每日选股日报和全市场股票分析结果。
- `run_sequoia_x_daily.ps1`：在本项目中更新 Sequoia-X 输出的入口脚本。

## 更新 Sequoia-X 输出

```powershell
cd E:\我的文档\股票分析
.\run_sequoia_x_daily.ps1
```

如果数据源同步不稳定，可以使用本地已有数据：

```powershell
.\run_sequoia_x_daily.ps1 -NoSyncLatest
```

## 注意

本仓库不提交任何 `.ssh` 私钥或嵌套 `.git` 元数据。
