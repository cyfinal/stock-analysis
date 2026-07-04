# Sequoia-X Engine Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Sequoia-X stock-picking strategy engine into `E:\我的文档\股票分析` so future work can happen from the stock-analysis repository.

**Architecture:** Keep `sequoia-x-engine/` as the self-contained Python engine and keep `sequoia-x/` as the generated-output directory. The root `run_sequoia_x_daily.ps1` calls the local engine, then copies the latest Markdown and CSV outputs into the output directory.

**Tech Stack:** PowerShell, Python 3.10+, pandas, baostock, akshare, pytest, SQLite.

---

### Task 1: Copy Engine Files

**Files:**
- Create: `sequoia-x-engine/sequoia_x/`
- Create: `sequoia-x-engine/scripts/`
- Create: `sequoia-x-engine/tests/`
- Create: `sequoia-x-engine/data/sequoia_v2.db`
- Create: `sequoia-x-engine/pyproject.toml`
- Create: `sequoia-x-engine/uv.lock`

- [x] Copy strategy source, report scripts, tests, reports, and local SQLite database from the old Sequoia-X checkout.
- [x] Exclude `.git`, `.venv`, cache directories, and egg-info metadata.

### Task 2: Local Runner

**Files:**
- Modify: `run_sequoia_x_daily.ps1`
- Create: `sequoia-x-engine/setup_env.ps1`

- [x] Update the root runner so default `EngineRoot` is `sequoia-x-engine` under the stock-analysis repository.
- [x] Add an environment setup script that creates `.venv` and installs the engine package.

### Task 3: Repository Hygiene

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`

- [x] Ignore the engine virtual environment, local SQLite database, Python caches, `.ssh`, and nested `.git` metadata.
- [x] Document first-time setup, daily run commands, outputs, and GitHub commit rules.

### Task 4: Verification

**Files:**
- Verify: `sequoia-x-engine/scripts/codex_daily_report.py`
- Verify: `sequoia-x-engine/scripts/export_all_stocks_analysis.py`
- Verify: `run_sequoia_x_daily.ps1`

- [x] Run Python compilation checks for the migrated scripts.
- [x] Run focused pytest coverage for report and export behavior.
- [x] Run the root daily wrapper in local-only mode and confirm outputs update under `sequoia-x/`.

### Task 5: Publish

**Files:**
- Commit all intended source, script, doc, and output changes.
- Push `main` to `https://github.com/cyfinal/stock-analysis`.
