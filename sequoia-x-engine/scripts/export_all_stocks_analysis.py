"""Export one-row-per-stock analysis for the latest local trading day."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

try:
    from scripts.codex_daily_report import (
        DEFAULT_STRATEGY_REASONS,
        get_latest_market_date,
        resolve_stock_names,
    )
except ModuleNotFoundError:
    from codex_daily_report import (
        DEFAULT_STRATEGY_REASONS,
        get_latest_market_date,
        resolve_stock_names,
    )
from sequoia_x.core.config import get_settings
from sequoia_x.data.engine import DataEngine
from sequoia_x.strategy.base import BaseStrategy
from sequoia_x.strategy.high_tight_flag import HighTightFlagStrategy
from sequoia_x.strategy.limit_up_shakeout import LimitUpShakeoutStrategy
from sequoia_x.strategy.ma_volume import MaVolumeStrategy
from sequoia_x.strategy.private_placement import PrivatePlacementStrategy
from sequoia_x.strategy.rps_breakout import RpsBreakoutStrategy
from sequoia_x.strategy.turtle_trade import TurtleTradeStrategy
from sequoia_x.strategy.uptrend_limit_down import UptrendLimitDownStrategy


FIELDNAMES = [
    "股票代码",
    "股票名称",
    "最新数据日期",
    "最新收盘价",
    "是否命中",
    "命中策略",
    "选股理由",
]


def load_strategy_results_from_report(report_path: str | Path) -> dict[str, set[str]]:
    text = Path(report_path).read_text(encoding="utf-8")
    results: dict[str, set[str]] = {}
    pattern = re.compile(
        r"^- (?P<strategy>\w+Strategy)：(?:候选 \d+ 只(?:，当日数据 \d+ 只)?，展示 Top \d+|(?P<count>\d+) 只)\n  (?P<symbols>[0-9, ]+)$",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        symbols = [
            symbol.strip()
            for symbol in match.group("symbols").split(",")
            if symbol.strip()
        ]
        results[match.group("strategy")] = set(symbols)

    for strategy_name in DEFAULT_STRATEGY_REASONS:
        results.setdefault(strategy_name, set())
    return results


def write_all_stocks_csv(
    *,
    db_path: str,
    output_dir: str | Path,
    results: dict[str, set[str]],
) -> tuple[Path, int, int, dict[str, int]]:
    with sqlite3.connect(db_path) as conn:
        symbols = [row[0] for row in conn.execute("SELECT DISTINCT symbol FROM stock_daily ORDER BY symbol")]
        latest = dict(conn.execute("SELECT symbol, MAX(date) FROM stock_daily GROUP BY symbol"))
        latest_close = dict(
            conn.execute(
                """
                SELECT symbol, close
                FROM stock_daily
                WHERE (symbol, date) IN (
                    SELECT symbol, MAX(date)
                    FROM stock_daily
                    GROUP BY symbol
                )
                """
            )
        )

    stock_names = resolve_stock_names(symbols)
    as_of_date = get_latest_market_date(db_path) or "latest"
    output_path = Path(output_dir) / f"{as_of_date}_all_stocks_analysis.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    selected_count = 0
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for symbol in symbols:
            hit_strategies = [name for name, selected in results.items() if symbol in selected]
            if hit_strategies:
                selected_count += 1
            reasons = [
                DEFAULT_STRATEGY_REASONS.get(strategy_name, "满足该策略的选股条件。")
                for strategy_name in hit_strategies
            ]
            writer.writerow(
                {
                    "股票代码": symbol,
                    "股票名称": stock_names.get(symbol, ""),
                    "最新数据日期": latest.get(symbol, ""),
                    "最新收盘价": latest_close.get(symbol, ""),
                    "是否命中": "是" if hit_strategies else "否",
                    "命中策略": "; ".join(hit_strategies),
                    "选股理由": "; ".join(reasons),
                }
            )

    return output_path, len(symbols), selected_count, {name: len(selected) for name, selected in results.items()}


def export_all_stocks_analysis(*, output_dir: str | Path = "reports") -> tuple[Path, int, int, dict[str, int]]:
    os.environ.setdefault(
        "FEISHU_WEBHOOK_URL",
        "https://open.feishu.cn/open-apis/bot/v2/hook/codex-disabled",
    )
    load_dotenv(".env")

    settings = get_settings()
    engine = DataEngine(settings)
    strategies: list[BaseStrategy] = [
        MaVolumeStrategy(engine=engine, settings=settings),
        TurtleTradeStrategy(engine=engine, settings=settings),
        HighTightFlagStrategy(engine=engine, settings=settings),
        LimitUpShakeoutStrategy(engine=engine, settings=settings),
        UptrendLimitDownStrategy(engine=engine, settings=settings),
        RpsBreakoutStrategy(engine=engine, settings=settings),
        PrivatePlacementStrategy(engine=engine, settings=settings),
    ]
    results = {type(strategy).__name__: set(strategy.run()) for strategy in strategies}

    return write_all_stocks_csv(
        db_path=settings.db_path,
        output_dir=output_dir,
        results=results,
    )


def export_all_stocks_analysis_from_report(
    *,
    report_path: str | Path,
    output_dir: str | Path = "reports",
) -> tuple[Path, int, int, dict[str, int]]:
    os.environ.setdefault(
        "FEISHU_WEBHOOK_URL",
        "https://open.feishu.cn/open-apis/bot/v2/hook/codex-disabled",
    )
    load_dotenv(".env")
    settings = get_settings()
    results = load_strategy_results_from_report(report_path)
    return write_all_stocks_csv(
        db_path=settings.db_path,
        output_dir=output_dir,
        results=results,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export all-stock Sequoia-X analysis CSV.")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument(
        "--from-report",
        default=None,
        help="Build CSV from an existing Markdown report instead of rerunning strategies.",
    )
    args = parser.parse_args()
    if args.from_report:
        output_path, rows, selected_count, strategy_counts = export_all_stocks_analysis_from_report(
            report_path=args.from_report,
            output_dir=args.output_dir,
        )
    else:
        output_path, rows, selected_count, strategy_counts = export_all_stocks_analysis(
            output_dir=args.output_dir,
        )
    print(output_path.resolve())
    print(f"rows={rows} selected_unique={selected_count}")
    print(strategy_counts)


if __name__ == "__main__":
    main()
