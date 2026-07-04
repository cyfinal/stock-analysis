"""Codex-facing daily report runner for Sequoia-X.

This keeps the original strategy logic but prints a report instead of sending
Feishu webhook messages.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_STRATEGY_REASONS: dict[str, str] = {
    "MaVolumeStrategy": "5日均线上穿20日均线，且成交量大于20日均量1.5倍。",
    "TurtleTradeStrategy": "收盘价突破前20个交易日高点，成交额过亿，且当日阳线真涨。",
    "HighTightFlagStrategy": "高而窄旗形整理后放量突破。",
    "LimitUpShakeoutStrategy": "涨停后洗盘回踩确认，趋势仍保持强势。",
    "UptrendLimitDownStrategy": "上升趋势中出现跌停反包或情绪修复信号。",
    "RpsBreakoutStrategy": "相对强度RPS领先，并出现价格突破。",
    "PrivatePlacementStrategy": "近7日出现定向增发公告。",
}


@dataclass(frozen=True)
class StockTradeInfo:
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    prev_close: float | None
    pct_change: float | None
    volume_ratio: float | None
    score: float


def select_top_symbols(
    symbols: Sequence[str],
    trade_infos: dict[str, StockTradeInfo],
    *,
    limit: int = 5,
) -> list[str]:
    return sorted(
        symbols,
        key=lambda symbol: (
            trade_infos.get(symbol).score if trade_infos.get(symbol) else float("-inf"),
            trade_infos.get(symbol).pct_change if trade_infos.get(symbol) and trade_infos[symbol].pct_change is not None else float("-inf"),
            trade_infos.get(symbol).turnover if trade_infos.get(symbol) else float("-inf"),
        ),
        reverse=True,
    )[:limit]


def format_trade_info(info: StockTradeInfo) -> str:
    pct = "N/A" if info.pct_change is None else f"{info.pct_change:.2f}%"
    volume_ratio = "N/A" if info.volume_ratio is None else f"{info.volume_ratio:.2f}"
    return (
        f"交易信息：日期 {info.date}，开 {info.open:.2f}，高 {info.high:.2f}，"
        f"低 {info.low:.2f}，收 {info.close:.2f}，涨跌幅 {pct}，"
        f"量比 {volume_ratio}，成交额 {info.turnover / 100_000_000:.2f} 亿"
    )


def format_holding_plan(strategy_name: str, info: StockTradeInfo) -> str:
    reference_price = info.close
    signal_stop = info.low
    hard_stop = reference_price * 0.92
    first_trim = reference_price * 1.12
    second_trim = reference_price * 1.20

    strategy_exit = {
        "MaVolumeStrategy": "收盘跌破20日线或放量启动后3个交易日不能继续走强，退出。",
        "TurtleTradeStrategy": "跌破10日线或最高价回撤 10%，剩余仓位退出。",
        "HighTightFlagStrategy": "跌回旗形整理区间或跌破突破日低点，退出。",
        "LimitUpShakeoutStrategy": "跌破洗盘低点或3个交易日内不能重新转强，退出。",
        "UptrendLimitDownStrategy": "1-3个交易日没有反包修复或继续创新低，退出。",
        "RpsBreakoutStrategy": "跌回突破平台、RPS强度掉队或最高价回撤 10%，退出。",
        "PrivatePlacementStrategy": "公告驱动不单独持有；跌破20日线或事件兑现后走弱，退出。",
    }.get(strategy_name, "买入理由失效、跌破关键低点或最高价回撤 10%，退出。")

    return (
        f"持有/减仓：参考买入 {reference_price:.2f}；跌破 {signal_stop:.2f} 视为信号失效，"
        f"硬止损参考 {hard_stop:.2f}；首次减仓 {first_trim:.2f} 附近减 1/3，"
        f"第二次减仓 {second_trim:.2f} 附近再减 1/3；{strategy_exit}"
    )


def format_report(
    *,
    as_of_date: str,
    update_count: int,
    results: dict[str, list[str]],
    stock_names: dict[str, str] | None = None,
    strategy_reasons: dict[str, str] | None = None,
    trade_infos: dict[str, StockTradeInfo] | None = None,
    max_symbols_per_strategy: int = 5,
) -> str:
    stock_names = stock_names or {}
    strategy_reasons = strategy_reasons or DEFAULT_STRATEGY_REASONS
    trade_infos = trade_infos or {}

    lines = [
        f"# Sequoia-X 选股日报",
        f"日期：{as_of_date}",
        f"增量数据：{update_count} 条",
        "",
        "## 策略结果",
        f"展示规则：每个策略按综合强度分最多展示 Top {max_symbols_per_strategy}；综合强度分参考当日涨跌幅、量比、成交额和收盘位置。",
    ]

    total = 0
    for strategy_name, symbols in results.items():
        current_symbols = [
            symbol
            for symbol in symbols
            if not trade_infos or (trade_infos.get(symbol) and trade_infos[symbol].date == as_of_date)
        ]
        top_symbols = select_top_symbols(current_symbols, trade_infos, limit=max_symbols_per_strategy)
        total += len(top_symbols)
        if top_symbols:
            lines.append(
                f"- {strategy_name}：候选 {len(symbols)} 只，当日数据 {len(current_symbols)} 只，展示 Top {len(top_symbols)}"
            )
            lines.append(f"  {', '.join(top_symbols)}")
            reason = strategy_reasons.get(strategy_name, "满足该策略的选股条件。")
            for symbol in top_symbols:
                name = stock_names.get(symbol, "").strip()
                display_name = f" {name}" if name else ""
                lines.append(f"  - {symbol}{display_name}｜理由：{reason}")
                info = trade_infos.get(symbol)
                if info:
                    lines.append(f"    - {format_trade_info(info)}")
                    lines.append(f"    - {format_holding_plan(strategy_name, info)}")
        else:
            lines.append(f"- {strategy_name}：无")

    lines.extend(["", f"合计：{total} 只"])
    if total == 0:
        lines.append("今天没有策略命中的股票。")

    return "\n".join(lines)


def write_report_file(
    report: str,
    *,
    as_of_date: str,
    output_dir: str | Path = "reports",
) -> Path:
    output_path = Path(output_dir) / f"{as_of_date}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return output_path


def build_latest_sync_tasks(
    symbol_dates: Sequence[tuple[str, str | None]],
    *,
    today_str: str,
    start_date: str,
    to_baostock_code: Callable[[str], str],
) -> list[tuple[str, str, str, str]]:
    tasks: list[tuple[str, str, str, str]] = []
    for symbol, last_date in symbol_dates:
        if last_date and last_date >= today_str:
            continue
        start = start_date
        if last_date:
            start = (date.fromisoformat(last_date) + timedelta(days=1)).strftime("%Y-%m-%d")
        tasks.append((symbol, to_baostock_code(symbol), start, today_str))
    return tasks


def upsert_daily_rows(db_path: str, rows: list[list[str]]) -> int:
    clean_rows: list[tuple[str, str, float, float, float, float, float, float]] = []
    for row in rows:
        if len(row) < 8:
            continue
        symbol, trade_date, open_, high, low, close, volume, turnover = row[:8]
        try:
            values = (
                symbol,
                trade_date,
                float(open_),
                float(high),
                float(low),
                float(close),
                float(volume),
                float(turnover),
            )
        except (TypeError, ValueError):
            continue
        if values[5] != values[5] or values[6] <= 0:
            continue
        clean_rows.append(values)

    if not clean_rows:
        return 0

    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO stock_daily
                (symbol, date, open, high, low, close, volume, turnover)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                turnover = excluded.turnover
            """,
            clean_rows,
        )
        conn.commit()
    return len(clean_rows)


def _chunked_tasks(
    tasks: Sequence[tuple[str, str, str, str]],
    size: int,
) -> list[list[tuple[str, str, str, str]]]:
    if size <= 0:
        raise ValueError("size must be positive")
    return [list(tasks[idx : idx + size]) for idx in range(0, len(tasks), size)]


def _load_default_fetcher() -> Callable[[list[tuple[str, str, str, str]]], list[list[str]]]:
    try:
        from scripts.backfill_missing_symbols import fetch_batch_with_timeout
    except ModuleNotFoundError:
        from backfill_missing_symbols import fetch_batch_with_timeout

    return fetch_batch_with_timeout


def sync_latest_daily_bars(
    engine: object,
    *,
    batch_size: int = 80,
    workers: int = 1,
    target_date: str | None = None,
    fetcher: Callable[[list[tuple[str, str, str, str]]], list[list[str]]] | None = None,
) -> int:
    if fetcher is None:
        fetcher = _load_default_fetcher()

    today_str = target_date or date.today().strftime("%Y-%m-%d")
    with closing(sqlite3.connect(engine.db_path)) as conn:
        symbol_dates = conn.execute(
            "SELECT symbol, MAX(date) FROM stock_daily GROUP BY symbol ORDER BY symbol"
        ).fetchall()

    if not symbol_dates:
        return 0

    tasks = build_latest_sync_tasks(
        symbol_dates,
        today_str=today_str,
        start_date=engine.start_date,
        to_baostock_code=engine._to_baostock_code,
    )
    if not tasks:
        return 0

    total = 0
    for batch in _chunked_tasks(tasks, batch_size):
        n_workers = min(workers, len(batch))
        if n_workers <= 1:
            batch_results = [fetcher(batch)]
        else:
            task_chunks = [batch[idx::n_workers] for idx in range(n_workers)]
            with Pool(n_workers) as pool:
                batch_results = pool.map(fetcher, task_chunks)
        rows: list[list[str]] = []
        for result in batch_results:
            rows.extend(result)
        total += upsert_daily_rows(engine.db_path, rows)
    return total


def get_update_count(engine: object, *, sync_latest: bool = False) -> int:
    if not sync_latest:
        return 0
    return sync_latest_daily_bars(engine)


def _count_rows(db_path: str) -> int:
    if not Path(db_path).exists():
        return 0
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM stock_daily").fetchone()
    return int(row[0] or 0)


def get_latest_market_date(db_path: str) -> str | None:
    if not Path(db_path).exists():
        return None
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute("SELECT MAX(date) FROM stock_daily").fetchone()
    return str(row[0]) if row and row[0] else None


def build_trade_infos(db_path: str, symbols: Sequence[str]) -> dict[str, StockTradeInfo]:
    unique_symbols = list(dict.fromkeys(symbols))
    if not unique_symbols or not Path(db_path).exists():
        return {}

    placeholders = ",".join("?" for _ in unique_symbols)
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            f"""
            SELECT symbol, date, open, high, low, close, volume, turnover
            FROM stock_daily
            WHERE symbol IN ({placeholders})
            ORDER BY symbol, date
            """,
            unique_symbols,
        ).fetchall()

    grouped: dict[str, list[tuple]] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)

    infos: dict[str, StockTradeInfo] = {}
    for symbol, symbol_rows in grouped.items():
        if not symbol_rows:
            continue
        latest = symbol_rows[-1]
        prev = symbol_rows[-2] if len(symbol_rows) >= 2 else None
        _, trade_date, open_, high, low, close, volume, turnover = latest
        prev_close = float(prev[5]) if prev else None
        pct_change = None
        if prev_close and prev_close != 0:
            pct_change = (float(close) - prev_close) / prev_close * 100

        previous_volumes = [float(row[6]) for row in symbol_rows[-21:-1] if row[6] is not None]
        volume_ratio = None
        if previous_volumes:
            avg_volume = sum(previous_volumes) / len(previous_volumes)
            if avg_volume:
                volume_ratio = float(volume) / avg_volume

        day_range = float(high) - float(low)
        close_position = 0.5 if day_range == 0 else (float(close) - float(low)) / day_range
        turnover_yi = float(turnover) / 100_000_000
        score = (
            (pct_change or 0)
            + min(volume_ratio or 0, 5) * 2
            + min(turnover_yi, 20) * 0.2
            + close_position * 2
        )
        infos[symbol] = StockTradeInfo(
            symbol=symbol,
            date=str(trade_date),
            open=float(open_),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(volume),
            turnover=float(turnover),
            prev_close=prev_close,
            pct_change=pct_change,
            volume_ratio=volume_ratio,
            score=score,
        )

    return infos


def resolve_stock_names(symbols: list[str]) -> dict[str, str]:
    """Return stock names keyed by 6-digit symbol, falling back silently on failures."""
    if not symbols:
        return {}

    try:
        import baostock as bs
    except Exception:
        return {}

    unique_symbols = set(dict.fromkeys(symbols))
    mapping: dict[str, str] = {}
    login_result = bs.login()
    if getattr(login_result, "error_code", "1") != "0":
        return mapping

    try:
        rs = bs.query_stock_basic(code_name="", code="")
        while rs.next():
            row = rs.get_row_data()
            if len(row) > 1:
                symbol = row[0].split(".")[-1]
                if symbol in unique_symbols and row[1]:
                    mapping[symbol] = row[1]
    except Exception:
        return mapping
    finally:
        bs.logout()

    return mapping


def build_selection_report(*, backfill_if_empty: bool = False, sync_latest: bool = True) -> tuple[str, str]:
    os.environ.setdefault(
        "FEISHU_WEBHOOK_URL",
        "https://open.feishu.cn/open-apis/bot/v2/hook/codex-disabled",
    )

    from dotenv import load_dotenv

    load_dotenv()

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

    settings = get_settings()
    engine = DataEngine(settings)

    if backfill_if_empty and _count_rows(settings.db_path) == 0:
        symbols = engine.get_all_symbols()
        if symbols:
            engine.backfill(symbols)

    update_count = get_update_count(engine, sync_latest=sync_latest)

    strategies: list[BaseStrategy] = [
        MaVolumeStrategy(engine=engine, settings=settings),
        TurtleTradeStrategy(engine=engine, settings=settings),
        HighTightFlagStrategy(engine=engine, settings=settings),
        LimitUpShakeoutStrategy(engine=engine, settings=settings),
        UptrendLimitDownStrategy(engine=engine, settings=settings),
        RpsBreakoutStrategy(engine=engine, settings=settings),
        PrivatePlacementStrategy(engine=engine, settings=settings),
    ]

    results = {type(strategy).__name__: strategy.run() for strategy in strategies}
    selected_symbols = [
        symbol
        for symbols in results.values()
        for symbol in symbols
    ]
    trade_infos = build_trade_infos(settings.db_path, selected_symbols)
    stock_names = resolve_stock_names(selected_symbols)
    as_of_date = get_latest_market_date(settings.db_path) or date.today().strftime("%Y-%m-%d")
    report = format_report(
        as_of_date=as_of_date,
        update_count=update_count,
        results=results,
        stock_names=stock_names,
        trade_infos=trade_infos,
    )
    return report, as_of_date


def run_selection_report(*, backfill_if_empty: bool = False, sync_latest: bool = True) -> str:
    report, _ = build_selection_report(
        backfill_if_empty=backfill_if_empty,
        sync_latest=sync_latest,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a Sequoia-X report for Codex.")
    parser.add_argument(
        "--backfill-if-empty",
        action="store_true",
        help="Run initial historical backfill when the local database is empty.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory where the Markdown report file will be saved.",
    )
    parser.add_argument(
        "--no-sync-latest",
        action="store_true",
        help="Skip baostock refresh and use the latest local trading-day data only.",
    )
    args = parser.parse_args()
    report, as_of_date = build_selection_report(
        backfill_if_empty=args.backfill_if_empty,
        sync_latest=not args.no_sync_latest,
    )
    print(report)
    saved_path = write_report_file(
        report,
        as_of_date=as_of_date,
        output_dir=args.output_dir,
    )
    print(f"\nReport saved to: {saved_path}")


if __name__ == "__main__":
    main()
