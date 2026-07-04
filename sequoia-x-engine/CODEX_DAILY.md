# Codex Daily Stock Pick Automation

This project is a local Codex wrapper around `sngyai/Sequoia-X`.

## Daily job

Codex runs this project every day at 08:00 Asia/Shanghai and posts the report
back to Codex.

Command used by the automation:

```powershell
& '.venv\Scripts\python.exe' 'scripts\codex_daily_report.py' --backfill-if-empty
```

## Behavior

- The script reuses Sequoia-X data loading and strategy classes.
- It does not call Feishu. It prints a Markdown report for Codex instead.
- It also saves the Markdown report to `reports/YYYY-MM-DD.md`.
- By default it refreshes the latest baostock daily bars with a batched upsert
  path before running strategies. Use `--no-sync-latest` only when a local-only
  run is needed.
- If `data/sequoia_v2.db` is empty, the first run performs a historical backfill.
- Morning runs use the latest data available from the local database and data
  provider, which normally means the previous trading day's signal before the
  market opens.

## Manual run

```powershell
cd C:\Users\Admin\Documents\Codex\2026-06-28\sequoia-x-daily
& '.venv\Scripts\python.exe' 'scripts\codex_daily_report.py'
```
