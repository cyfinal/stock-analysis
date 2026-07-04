import unittest

import pandas as pd

from scripts.backtest_report import build_trade_records, summarize_records


class BacktestReportTests(unittest.TestCase):
    def test_build_trade_records_uses_next_close_entry_and_horizon_exit(self) -> None:
        dates = pd.date_range("2026-06-01", periods=7, freq="D")
        prices = pd.DataFrame(
            [
                {"symbol": "000001", "date": date, "close": close}
                for date, close in zip(dates, [10, 11, 12, 13, 14, 15, 16])
            ]
            + [
                {"symbol": "000002", "date": date, "close": close}
                for date, close in zip(dates, [20, 20, 20, 20, 20, 20, 20])
            ]
        )

        records = build_trade_records(
            prices,
            signals={"DemoStrategy": {"000001": [dates[0]]}},
            holding_days=5,
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.entry_date.strftime("%Y-%m-%d"), "2026-06-02")
        self.assertEqual(record.exit_date.strftime("%Y-%m-%d"), "2026-06-07")
        self.assertAlmostEqual(record.return_pct, (16 - 11) / 11 * 100)
        self.assertAlmostEqual(record.benchmark_return_pct, ((16 - 11) / 11 * 100 + 0) / 2)

    def test_summarize_records_reports_win_rate_and_average_excess(self) -> None:
        dates = pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-03"])
        prices = pd.DataFrame(
            [
                {"symbol": "000001", "date": dates[0], "close": 10},
                {"symbol": "000001", "date": dates[1], "close": 10},
                {"symbol": "000001", "date": dates[2], "close": 12},
                {"symbol": "000002", "date": dates[0], "close": 10},
                {"symbol": "000002", "date": dates[1], "close": 10},
                {"symbol": "000002", "date": dates[2], "close": 9},
            ]
        )

        records = build_trade_records(
            prices,
            signals={"DemoStrategy": {"000001": [dates[0]], "000002": [dates[0]]}},
            holding_days=1,
        )
        summary = summarize_records(records)

        self.assertEqual(summary["DemoStrategy"].trade_count, 2)
        self.assertAlmostEqual(summary["DemoStrategy"].win_rate_pct, 50.0)
        self.assertAlmostEqual(summary["DemoStrategy"].avg_return_pct, 5.0)


if __name__ == "__main__":
    unittest.main()
