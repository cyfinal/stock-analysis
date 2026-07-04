"""One-month historical backtest report for Sequoia-X price-based strategies."""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

try:
    from scripts.codex_daily_report import DEFAULT_STRATEGY_REASONS, resolve_stock_names
except ModuleNotFoundError:
    from codex_daily_report import DEFAULT_STRATEGY_REASONS, resolve_stock_names


PRICE_STRATEGIES = [
    "MaVolumeStrategy",
    "TurtleTradeStrategy",
    "HighTightFlagStrategy",
    "LimitUpShakeoutStrategy",
    "UptrendLimitDownStrategy",
    "RpsBreakoutStrategy",
]


@dataclass(frozen=True)
class TradeRecord:
    strategy: str
    symbol: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_close: float
    exit_close: float
    return_pct: float
    benchmark_return_pct: float

    @property
    def excess_return_pct(self) -> float:
        return self.return_pct - self.benchmark_return_pct


@dataclass(frozen=True)
class StrategySummary:
    trade_count: int
    win_rate_pct: float
    avg_return_pct: float
    median_return_pct: float
    avg_benchmark_return_pct: float
    avg_excess_return_pct: float


def load_prices(db_path: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql(
            """
            SELECT symbol, date, open, high, low, close, volume, turnover
            FROM stock_daily
            ORDER BY symbol, date
            """,
            conn,
        )

    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"])
    numeric_cols = ["open", "high", "low", "close", "volume", "turnover"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["symbol", "date", "close"])


def latest_signal_window(df: pd.DataFrame, trading_days: int = 20) -> list[pd.Timestamp]:
    dates = sorted(df["date"].dropna().unique())
    return [pd.Timestamp(d) for d in dates[-trading_days:]]


def _blank_signal_map() -> dict[str, dict[str, list[pd.Timestamp]]]:
    return {strategy: {} for strategy in PRICE_STRATEGIES}


def generate_price_signals(
    df: pd.DataFrame,
    *,
    signal_dates: list[pd.Timestamp],
) -> dict[str, dict[str, list[pd.Timestamp]]]:
    signals = _blank_signal_map()
    if df.empty or not signal_dates:
        return signals

    signal_date_set = set(pd.Timestamp(d) for d in signal_dates)
    work = df.sort_values(["symbol", "date"]).copy()
    grouped = work.groupby("symbol", group_keys=False)

    work["ma5"] = grouped["close"].transform(lambda s: s.rolling(5).mean())
    work["ma20"] = grouped["close"].transform(lambda s: s.rolling(20).mean())
    work["ma60"] = grouped["close"].transform(lambda s: s.rolling(60).mean())
    work["vol_ma20"] = grouped["volume"].transform(lambda s: s.rolling(20).mean())
    work["prev_close"] = grouped["close"].shift(1)
    work["prev2_close"] = grouped["close"].shift(2)
    work["prev_open"] = grouped["open"].shift(1)
    work["prev_volume"] = grouped["volume"].shift(1)
    work["prev2_volume"] = grouped["volume"].shift(2)
    work["prev_ma5"] = grouped["ma5"].shift(1)
    work["prev_ma20"] = grouped["ma20"].shift(1)
    work["prev_ma60"] = grouped["ma60"].shift(1)
    work["prev_high20"] = grouped["high"].transform(lambda s: s.shift(1).rolling(20).max())
    work["high40"] = grouped["high"].transform(lambda s: s.rolling(40).max())
    work["low40"] = grouped["low"].transform(lambda s: s.rolling(40).min())
    work["high10"] = grouped["high"].transform(lambda s: s.rolling(10).max())
    work["low10"] = grouped["low"].transform(lambda s: s.rolling(10).min())
    work["prev_vol20_mean"] = grouped["volume"].transform(lambda s: s.shift(1).rolling(20).mean())
    work["close_shift120"] = grouped["close"].shift(120)
    work["pct_change120"] = (work["close"] - work["close_shift120"]) / work["close_shift120"]
    work["roll_high120"] = grouped["high"].transform(lambda s: s.rolling(120, min_periods=60).max())

    for signal_date in signal_dates:
        day = work[work["date"] == signal_date].copy()
        if day.empty:
            continue

        ma_volume = day[
            (day["prev_ma5"] < day["prev_ma20"])
            & (day["ma5"] > day["ma20"])
            & (day["volume"] > day["vol_ma20"] * 1.5)
        ]
        _add_signals(signals, "MaVolumeStrategy", ma_volume["symbol"], signal_date)

        turtle = day[
            (day["close"] > day["prev_high20"])
            & (day["turnover"] > 100_000_000)
            & (day["close"] > day["open"])
            & (day["close"] > day["prev_close"])
        ]
        _add_signals(signals, "TurtleTradeStrategy", turtle["symbol"], signal_date)

        high_tight = day[
            (day["low40"] > 0)
            & (day["low10"] > 0)
            & (day["high40"] / day["low40"] > 1.6)
            & (day["high10"] / day["low10"] < 1.15)
            & (day["low10"] >= day["high40"] * 0.8)
            & (day["volume"] < day["prev_vol20_mean"] * 0.6)
        ]
        _add_signals(signals, "HighTightFlagStrategy", high_tight["symbol"], signal_date)

        shakeout = day[
            (day["prev_close"] >= day["prev2_close"] * 1.095)
            & (day["close"] < day["open"])
            & (day["volume"] > day["prev_volume"] * 2.0)
            & (day["low"] >= day["prev_close"])
        ]
        _add_signals(signals, "LimitUpShakeoutStrategy", shakeout["symbol"], signal_date)

        limit_down = day[
            (day["prev_ma20"] > day["prev_ma60"])
            & (day["close"] <= day["prev_close"] * 0.905)
            & (day["volume"] > day["vol_ma20"] * 2.0)
        ]
        _add_signals(signals, "UptrendLimitDownStrategy", limit_down["symbol"], signal_date)

        rps_day = day.dropna(subset=["pct_change120", "roll_high120"]).copy()
        if not rps_day.empty:
            rps_day["rps"] = rps_day["pct_change120"].rank(pct=True) * 100
            rps = rps_day[(rps_day["rps"] >= 90) & (rps_day["close"] >= rps_day["roll_high120"] * 0.90)]
            _add_signals(signals, "RpsBreakoutStrategy", rps["symbol"], signal_date)

    for strategy, by_symbol in signals.items():
        signals[strategy] = {
            symbol: dates
            for symbol, dates in by_symbol.items()
            if any(pd.Timestamp(d) in signal_date_set for d in dates)
        }
    return signals


def _add_signals(
    signals: dict[str, dict[str, list[pd.Timestamp]]],
    strategy: str,
    symbols: pd.Series,
    signal_date: pd.Timestamp,
) -> None:
    for symbol in symbols.astype(str).tolist():
        signals[strategy].setdefault(symbol, []).append(pd.Timestamp(signal_date))


def build_trade_records(
    prices: pd.DataFrame,
    *,
    signals: dict[str, dict[str, list[pd.Timestamp]]],
    holding_days: int = 5,
) -> list[TradeRecord]:
    if prices.empty:
        return []

    work = prices.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values(["symbol", "date"])
    date_index = {pd.Timestamp(d): i for i, d in enumerate(sorted(work["date"].unique()))}
    dates = sorted(date_index)

    closes = {
        symbol: group.set_index("date")["close"].sort_index()
        for symbol, group in work.groupby("symbol")
    }

    records: list[TradeRecord] = []
    for strategy, by_symbol in signals.items():
        for symbol, signal_dates in by_symbol.items():
            series = closes.get(symbol)
            if series is None:
                continue
            for signal_date in signal_dates:
                signal_date = pd.Timestamp(signal_date)
                if signal_date not in date_index:
                    continue
                entry_idx = date_index[signal_date] + 1
                exit_idx = entry_idx + holding_days
                if exit_idx >= len(dates):
                    continue

                entry_date = dates[entry_idx]
                exit_date = dates[exit_idx]
                if entry_date not in series.index or exit_date not in series.index:
                    continue

                entry_close = float(series.loc[entry_date])
                exit_close = float(series.loc[exit_date])
                if entry_close <= 0:
                    continue

                return_pct = (exit_close - entry_close) / entry_close * 100
                benchmark_return_pct = _benchmark_return_pct(work, entry_date, exit_date)
                records.append(
                    TradeRecord(
                        strategy=strategy,
                        symbol=symbol,
                        signal_date=signal_date,
                        entry_date=entry_date,
                        exit_date=exit_date,
                        entry_close=entry_close,
                        exit_close=exit_close,
                        return_pct=return_pct,
                        benchmark_return_pct=benchmark_return_pct,
                    )
                )

    return records


def _benchmark_return_pct(prices: pd.DataFrame, entry_date: pd.Timestamp, exit_date: pd.Timestamp) -> float:
    entry = prices[prices["date"] == entry_date][["symbol", "close"]].rename(columns={"close": "entry"})
    exit_ = prices[prices["date"] == exit_date][["symbol", "close"]].rename(columns={"close": "exit"})
    merged = entry.merge(exit_, on="symbol")
    merged = merged[merged["entry"] > 0]
    if merged.empty:
        return 0.0
    returns = (merged["exit"] - merged["entry"]) / merged["entry"] * 100
    return float(returns.mean())


def summarize_records(records: list[TradeRecord]) -> dict[str, StrategySummary]:
    summary: dict[str, StrategySummary] = {}
    by_strategy: dict[str, list[TradeRecord]] = {}
    for record in records:
        by_strategy.setdefault(record.strategy, []).append(record)

    for strategy, strategy_records in by_strategy.items():
        returns = pd.Series([r.return_pct for r in strategy_records])
        benchmark_returns = pd.Series([r.benchmark_return_pct for r in strategy_records])
        excess_returns = pd.Series([r.excess_return_pct for r in strategy_records])
        summary[strategy] = StrategySummary(
            trade_count=len(strategy_records),
            win_rate_pct=float((returns > 0).mean() * 100),
            avg_return_pct=float(returns.mean()),
            median_return_pct=float(returns.median()),
            avg_benchmark_return_pct=float(benchmark_returns.mean()),
            avg_excess_return_pct=float(excess_returns.mean()),
        )
    return summary


def format_backtest_report(
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    prices: pd.DataFrame,
    signal_dates: list[pd.Timestamp],
    signals: dict[str, dict[str, list[pd.Timestamp]]],
    records: list[TradeRecord],
    stock_names: dict[str, str],
    holding_days: int,
) -> str:
    summary = summarize_records(records)
    supported_symbols = prices["symbol"].nunique() if not prices.empty else 0
    data_start = prices["date"].min().strftime("%Y-%m-%d") if not prices.empty else "N/A"
    data_end = prices["date"].max().strftime("%Y-%m-%d") if not prices.empty else "N/A"

    lines = [
        "# Sequoia-X 近一个月策略回测报告",
        "",
        f"- 回测信号区间：{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}",
        f"- 本地数据范围：{data_start} 至 {data_end}",
        f"- 样本股票数：{supported_symbols}",
        f"- 信号交易日数：{len(signal_dates)}",
        f"- 交易假设：信号日后第1个交易日收盘买入，持有 {holding_days} 个交易日后收盘卖出。",
        "- 基准：同一买入/卖出日期内样本股票等权平均收益。",
        "- 重要限制：本地数据库按 baostock 当前上市 A 股列表回填；个别交易日会因停牌、新股上市或数据源缺口导致实际有 K 线的股票数少于全列表。结果仅用于策略历史检验，不构成投资建议。",
        "",
        "## 策略汇总",
        "",
        "| 策略 | 信号数 | 可评估交易 | 胜率 | 平均收益 | 中位收益 | 基准平均 | 平均超额 | 判断 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for strategy in PRICE_STRATEGIES:
        signal_count = sum(len(dates) for dates in signals.get(strategy, {}).values())
        item = summary.get(strategy)
        if item is None:
            lines.append(f"| {strategy} | {signal_count} | 0 | N/A | N/A | N/A | N/A | N/A | 样本内无可评估交易 |")
            continue
        judgment = _judge_strategy(item)
        lines.append(
            f"| {strategy} | {signal_count} | {item.trade_count} | "
            f"{item.win_rate_pct:.1f}% | {item.avg_return_pct:.2f}% | {item.median_return_pct:.2f}% | "
            f"{item.avg_benchmark_return_pct:.2f}% | {item.avg_excess_return_pct:.2f}% | {judgment} |"
        )

    lines.extend(
        [
            "",
            "## 策略解释",
            "",
        ]
    )
    for strategy in PRICE_STRATEGIES:
        lines.append(f"- {strategy}：{DEFAULT_STRATEGY_REASONS.get(strategy, '满足该策略的选股条件。')}")
    lines.append("- PrivatePlacementStrategy：依赖定向增发公告接口，当前本地 K 线库无法还原一个月内每日公告快照，本次不纳入收益回测。")

    lines.extend(["", "## 代表性交易", ""])
    for strategy in PRICE_STRATEGIES:
        strategy_records = [r for r in records if r.strategy == strategy]
        if not strategy_records:
            continue
        lines.append(f"### {strategy}")
        top_records = sorted(strategy_records, key=lambda r: r.return_pct, reverse=True)[:5]
        for record in top_records:
            name = stock_names.get(record.symbol, "")
            display_name = f" {name}" if name else ""
            lines.append(
                f"- {record.symbol}{display_name}：信号 {record.signal_date.strftime('%Y-%m-%d')}，"
                f"买入 {record.entry_date.strftime('%Y-%m-%d')}，卖出 {record.exit_date.strftime('%Y-%m-%d')}，"
                f"收益 {record.return_pct:.2f}%，超额 {record.excess_return_pct:.2f}%"
            )
        lines.append("")

    lines.extend(["## 结论", "", _overall_conclusion(summary)])
    return "\n".join(lines).rstrip() + "\n"


def _judge_strategy(item: StrategySummary) -> str:
    if item.trade_count < 5:
        return "样本过少"
    if item.avg_excess_return_pct > 1 and item.win_rate_pct >= 50:
        return "样本内有效"
    if item.avg_excess_return_pct > 0:
        return "略优于基准"
    return "样本内未验证"


def _overall_conclusion(summary: dict[str, StrategySummary]) -> str:
    evaluable = [(strategy, item) for strategy, item in summary.items() if item.trade_count >= 5]
    if not evaluable:
        return "近一个月可评估交易数不足，不能判断策略正确性。需要更完整的全市场数据和更长周期样本。"

    ranked = sorted(evaluable, key=lambda pair: pair[1].avg_excess_return_pct, reverse=True)
    best_strategy, best = ranked[0]
    worst_strategy, worst = ranked[-1]
    return (
        f"从当前本地全市场样本看，{best_strategy} 的平均超额收益最高（{best.avg_excess_return_pct:.2f}%），"
        f"{worst_strategy} 的平均超额收益最低（{worst.avg_excess_return_pct:.2f}%）。"
        "由于区间仅约一个月，本次结果只能说明短期样本内表现，不能证明策略长期有效。"
    )


def write_backtest_report(report: str, *, output_dir: str | Path, start_date: pd.Timestamp, end_date: pd.Timestamp) -> Path:
    output_path = Path(output_dir) / (
        f"backtest_{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return output_path


def run_backtest_report(
    *,
    db_path: str = "data/sequoia_v2.db",
    trading_days: int = 20,
    holding_days: int = 5,
    output_dir: str | Path = "reports",
    with_names: bool = False,
) -> Path:
    prices = load_prices(db_path)
    signal_dates = latest_signal_window(prices, trading_days=trading_days)
    if not signal_dates:
        raise RuntimeError("No local price data available for backtest.")

    signals = generate_price_signals(prices, signal_dates=signal_dates)
    records = build_trade_records(prices, signals=signals, holding_days=holding_days)
    selected_symbols = sorted({record.symbol for record in records})
    stock_names = resolve_stock_names(selected_symbols) if with_names else {}
    report = format_backtest_report(
        start_date=signal_dates[0],
        end_date=signal_dates[-1],
        prices=prices,
        signal_dates=signal_dates,
        signals=signals,
        records=records,
        stock_names=stock_names,
        holding_days=holding_days,
    )
    return write_backtest_report(
        report,
        output_dir=output_dir,
        start_date=signal_dates[0],
        end_date=signal_dates[-1],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a one-month Sequoia-X strategy backtest.")
    parser.add_argument("--db-path", default="data/sequoia_v2.db")
    parser.add_argument("--trading-days", type=int, default=20)
    parser.add_argument("--holding-days", type=int, default=5)
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--with-names", action="store_true", help="Resolve stock Chinese names via baostock.")
    args = parser.parse_args()

    path = run_backtest_report(
        db_path=args.db_path,
        trading_days=args.trading_days,
        holding_days=args.holding_days,
        output_dir=args.output_dir,
        with_names=args.with_names,
    )
    print(f"Backtest report saved to: {path}")


if __name__ == "__main__":
    main()
