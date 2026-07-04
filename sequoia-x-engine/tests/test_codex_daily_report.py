import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from scripts.codex_daily_report import (
    StockTradeInfo,
    build_latest_sync_tasks,
    format_report,
    format_holding_plan,
    get_update_count,
    select_top_symbols,
    sync_latest_daily_bars,
    upsert_daily_rows,
    write_report_file,
)


class CodexDailyReportTests(unittest.TestCase):
    def test_format_report_groups_selected_symbols_by_strategy(self) -> None:
        report = format_report(
            as_of_date="2026-06-28",
            update_count=42,
            results={
                "MaVolumeStrategy": ["000001", "600000"],
                "TurtleTradeStrategy": [],
            },
        )

        self.assertIn("Sequoia-X 选股日报", report)
        self.assertIn("日期：2026-06-28", report)
        self.assertIn("增量数据：42 条", report)
        self.assertIn("MaVolumeStrategy：候选 2 只，当日数据 2 只，展示 Top 2", report)
        self.assertIn("000001, 600000", report)
        self.assertIn("TurtleTradeStrategy：无", report)

    def test_format_report_includes_stock_names_and_reasons(self) -> None:
        report = format_report(
            as_of_date="2026-06-28",
            update_count=0,
            results={"MaVolumeStrategy": ["000001"]},
            stock_names={"000001": "平安银行"},
            strategy_reasons={"MaVolumeStrategy": "5日均线上穿20日均线，且成交量放大。"},
        )

        self.assertIn("000001 平安银行", report)
        self.assertIn("理由：5日均线上穿20日均线，且成交量放大。", report)

    def test_select_top_symbols_limits_each_strategy_to_five_by_score(self) -> None:
        symbols = ["000001", "000002", "000003", "000004", "000005", "000006"]
        trade_infos = {
            symbol: StockTradeInfo(
                symbol=symbol,
                date="2026-07-03",
                open=10.0,
                high=11.0,
                low=9.5,
                close=10.0 + idx,
                volume=1000.0,
                turnover=100000000.0 + idx,
                prev_close=9.8,
                pct_change=idx,
                volume_ratio=1.0 + idx,
                score=idx,
            )
            for idx, symbol in enumerate(symbols)
        }

        self.assertEqual(
            select_top_symbols(symbols, trade_infos, limit=5),
            ["000006", "000005", "000004", "000003", "000002"],
        )

    def test_format_report_shows_top_five_trade_info_and_holding_plan(self) -> None:
        symbols = ["000001", "000002", "000003", "000004", "000005", "000006"]
        trade_infos = {
            symbol: StockTradeInfo(
                symbol=symbol,
                date="2026-07-03",
                open=10.0,
                high=12.0,
                low=9.0,
                close=10.0 + idx,
                volume=1000.0,
                turnover=200000000.0,
                prev_close=9.5,
                pct_change=idx,
                volume_ratio=2.0,
                score=idx,
            )
            for idx, symbol in enumerate(symbols)
        }

        report = format_report(
            as_of_date="2026-07-03",
            update_count=0,
            results={"MaVolumeStrategy": symbols},
            stock_names={"000006": "示例股份"},
            trade_infos=trade_infos,
            strategy_reasons={"MaVolumeStrategy": "放量金叉。"},
        )

        self.assertIn("MaVolumeStrategy：候选 6 只，当日数据 6 只，展示 Top 5", report)
        self.assertIn("000006 示例股份", report)
        self.assertIn("交易信息：日期 2026-07-03", report)
        self.assertIn("涨跌幅 5.00%", report)
        self.assertIn("成交额 2.00 亿", report)
        self.assertIn("持有/减仓：参考买入 15.00", report)
        self.assertIn("首次减仓", report)
        self.assertNotIn("000001｜理由", report)

    def test_format_report_excludes_symbols_without_as_of_date_trade_info(self) -> None:
        report = format_report(
            as_of_date="2026-07-03",
            update_count=0,
            results={"TurtleTradeStrategy": ["000001", "000002"]},
            trade_infos={
                "000001": StockTradeInfo(
                    symbol="000001",
                    date="2026-07-02",
                    open=10.0,
                    high=12.0,
                    low=9.0,
                    close=12.0,
                    volume=1000.0,
                    turnover=200000000.0,
                    prev_close=10.0,
                    pct_change=20.0,
                    volume_ratio=5.0,
                    score=100.0,
                ),
                "000002": StockTradeInfo(
                    symbol="000002",
                    date="2026-07-03",
                    open=10.0,
                    high=11.0,
                    low=9.5,
                    close=10.5,
                    volume=1000.0,
                    turnover=100000000.0,
                    prev_close=10.0,
                    pct_change=5.0,
                    volume_ratio=2.0,
                    score=10.0,
                ),
            },
        )

        self.assertIn("TurtleTradeStrategy：候选 2 只，当日数据 1 只，展示 Top 1", report)
        self.assertIn("000002", report)
        self.assertNotIn("000001", report)

    def test_format_holding_plan_uses_strategy_specific_exit_language(self) -> None:
        info = StockTradeInfo(
            symbol="000001",
            date="2026-07-03",
            open=10.0,
            high=12.0,
            low=9.0,
            close=10.0,
            volume=1000.0,
            turnover=100000000.0,
            prev_close=9.8,
            pct_change=2.04,
            volume_ratio=2.0,
            score=5.0,
        )

        plan = format_holding_plan("TurtleTradeStrategy", info)

        self.assertIn("参考买入 10.00", plan)
        self.assertIn("跌破 9.00", plan)
        self.assertIn("10日线或最高价回撤 10%", plan)

    def test_write_report_file_saves_markdown_by_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = write_report_file(
                "# Daily report\n",
                as_of_date="2026-06-26",
                output_dir=tmp_dir,
            )

            self.assertEqual(path.name, "2026-06-26.md")
            self.assertEqual(path.read_text(encoding="utf-8"), "# Daily report\n")

    def test_get_update_count_skips_network_sync_by_default(self) -> None:
        class Engine:
            called = False

            def sync_today_bulk(self) -> int:
                self.called = True
                return 12

        engine = Engine()

        self.assertEqual(get_update_count(engine, sync_latest=False), 0)
        self.assertFalse(engine.called)

    def test_get_update_count_can_sync_when_requested(self) -> None:
        engine = object()

        with patch("scripts.codex_daily_report.sync_latest_daily_bars", return_value=12) as sync:
            self.assertEqual(get_update_count(engine, sync_latest=True), 12)
            sync.assert_called_once_with(engine)

    def test_build_latest_sync_tasks_starts_after_last_local_date(self) -> None:
        rows = [
            ("000001", "2026-06-26"),
            ("000002", "2026-06-30"),
            ("600000", None),
        ]

        tasks = build_latest_sync_tasks(
            rows,
            today_str="2026-06-30",
            start_date="2024-01-02",
            to_baostock_code=lambda symbol: f"bs.{symbol}",
        )

        self.assertEqual(
            tasks,
            [
                ("000001", "bs.000001", "2026-06-27", "2026-06-30"),
                ("600000", "bs.600000", "2024-01-02", "2026-06-30"),
            ],
        )

    def test_upsert_daily_rows_updates_existing_symbol_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = f"{tmp_dir}/daily.db"
            import sqlite3

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE stock_daily (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        date TEXT NOT NULL,
                        open REAL,
                        high REAL,
                        low REAL,
                        close REAL,
                        volume REAL,
                        turnover REAL,
                        UNIQUE (symbol, date)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO stock_daily
                    (symbol, date, open, high, low, close, volume, turnover)
                    VALUES ('000001', '2026-06-30', 1, 2, 0.5, 1.5, 100, 1000)
                    """
                )
                conn.commit()

            inserted = upsert_daily_rows(
                db_path,
                [
                    ["000001", "2026-06-30", "2", "3", "1", "2.5", "200", "2000"],
                    ["000002", "2026-06-30", "5", "6", "4", "5.5", "300", "3000"],
                ],
            )

            with closing(sqlite3.connect(db_path)) as conn:
                rows = conn.execute(
                    "SELECT symbol, date, close, volume FROM stock_daily ORDER BY symbol"
                ).fetchall()

            self.assertEqual(inserted, 2)
            self.assertEqual(
                rows,
                [
                    ("000001", "2026-06-30", 2.5, 200.0),
                    ("000002", "2026-06-30", 5.5, 300.0),
                ],
            )

    def test_sync_latest_daily_bars_can_run_without_multiprocessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = f"{tmp_dir}/daily.db"
            import sqlite3

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE stock_daily (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        date TEXT NOT NULL,
                        open REAL,
                        high REAL,
                        low REAL,
                        close REAL,
                        volume REAL,
                        turnover REAL,
                        UNIQUE (symbol, date)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO stock_daily
                    (symbol, date, open, high, low, close, volume, turnover)
                    VALUES ('000001', '2026-06-26', 1, 2, 0.5, 1.5, 100, 1000)
                    """
                )
                conn.commit()

            class Engine:
                start_date = "2024-01-02"

                def __init__(self, path: str) -> None:
                    self.db_path = path

                @staticmethod
                def _to_baostock_code(symbol: str) -> str:
                    return f"bs.{symbol}"

            calls = []

            def fetcher(tasks):
                calls.append(tasks)
                return [["000001", "2026-06-30", "2", "3", "1", "2.5", "200", "2000"]]

            inserted = sync_latest_daily_bars(
                Engine(db_path),
                batch_size=80,
                workers=1,
                target_date="2026-06-30",
                fetcher=fetcher,
            )

            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute(
                    "SELECT symbol, date, close FROM stock_daily WHERE symbol='000001' ORDER BY date DESC"
                ).fetchone()

            self.assertEqual(inserted, 1)
            self.assertEqual(
                calls,
                [[("000001", "bs.000001", "2026-06-27", "2026-06-30")]],
            )
            self.assertEqual(row, ("000001", "2026-06-30", 2.5))


if __name__ == "__main__":
    unittest.main()
