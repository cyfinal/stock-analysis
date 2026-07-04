"""Build the static web data file for the Sequoia-X daily results section."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


STRATEGY_LABELS = {
    "MaVolumeStrategy": "均线放量",
    "TurtleTradeStrategy": "海龟突破",
    "HighTightFlagStrategy": "高位紧旗",
    "LimitUpShakeoutStrategy": "涨停洗盘",
    "UptrendLimitDownStrategy": "趋势反包",
    "RpsBreakoutStrategy": "RPS突破",
    "PrivatePlacementStrategy": "定增事件",
}


def parse_report(report_path: Path) -> dict:
    text = report_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    report_date = ""
    incremental_rows = ""
    total_items = ""
    current_strategy = ""
    strategy_summaries: dict[str, dict] = {}
    items: list[dict] = []

    for line in lines:
        if line.startswith("日期："):
            report_date = line.split("：", 1)[1].strip()
            continue
        if line.startswith("增量数据："):
            incremental_rows = line.split("：", 1)[1].strip()
            continue
        if line.startswith("合计："):
            total_items = line.split("：", 1)[1].strip()
            continue

        if line.startswith("- ") and "Strategy：" in line:
            current_strategy = line[2:].split("：", 1)[0].strip()
            strategy_summaries.setdefault(
                current_strategy,
                {
                    "name": current_strategy,
                    "label": STRATEGY_LABELS.get(current_strategy, current_strategy),
                    "summary": line[2:].strip(),
                    "symbols": [],
                    "items": [],
                },
            )
            continue

        if current_strategy and line.startswith("  ") and "," in line and not line.startswith("  - "):
            symbols = [symbol.strip() for symbol in line.strip().split(",") if symbol.strip()]
            if symbols and all(symbol.isdigit() and len(symbol) == 6 for symbol in symbols):
                strategy_summaries[current_strategy]["symbols"] = symbols
            continue

        if line.startswith("  - ") and "｜理由：" in line:
            left, reason = line[4:].split("｜理由：", 1)
            code, name = left.split(" ", 1)
            item = {
                "strategy": current_strategy,
                "strategyLabel": STRATEGY_LABELS.get(current_strategy, current_strategy),
                "code": code,
                "name": name,
                "reason": reason,
            }
            items.append(item)
            if current_strategy:
                strategy_summaries[current_strategy]["items"].append(item)
            continue

        if line.startswith("    - 交易信息：") and items:
            info = line.split("交易信息：", 1)[1]
            values = {}
            for part in info.split("，"):
                if " " in part:
                    key, value = part.split(" ", 1)
                    values[key] = value
            items[-1].update(
                {
                    "date": values.get("日期", ""),
                    "open": values.get("开", ""),
                    "high": values.get("高", ""),
                    "low": values.get("低", ""),
                    "close": values.get("收", ""),
                    "changePct": values.get("涨跌幅", ""),
                    "volumeRatio": values.get("量比", ""),
                    "turnover": values.get("成交额", ""),
                }
            )
            continue

        if line.startswith("    - 持有/减仓：") and items:
            items[-1]["plan"] = line.split("持有/减仓：", 1)[1].strip()

    return {
        "reportDate": report_date,
        "incrementalRows": incremental_rows,
        "totalItems": total_items,
        "strategies": list(strategy_summaries.values()),
        "items": items,
    }


def parse_csv_summary(csv_path: Path) -> dict:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        header = next(reader)
        rows = list(reader)

    date_counts = Counter(row[2] for row in rows if len(row) > 2 and row[2])
    hits = [row for row in rows if len(row) > 4 and row[4] == "是"]
    strategy_counts: Counter[str] = Counter()
    for row in hits:
        for strategy_name in row[5].split(";"):
            strategy_name = strategy_name.strip()
            if strategy_name:
                strategy_counts[strategy_name] += 1

    return {
        "rows": len(rows),
        "header": header,
        "hitStocks": len(hits),
        "latestDataDates": [{"date": date, "count": count} for date, count in date_counts.most_common(8)],
        "strategyHitCounts": [
            {
                "name": name,
                "label": STRATEGY_LABELS.get(name, name),
                "count": count,
            }
            for name, count in strategy_counts.most_common()
        ],
    }


def build_payload(report_path: Path, csv_path: Path) -> dict:
    report = parse_report(report_path)
    csv_summary = parse_csv_summary(csv_path)
    return {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reportPath": report_path.as_posix(),
        "csvPath": csv_path.as_posix(),
        "report": report,
        "csvSummary": csv_summary,
    }


def write_js(payload: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    output_path.write_text(
        "window.SEQUOIA_DAILY_RESULTS = " + json_text + ";\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Update the static Sequoia-X web results data.")
    parser.add_argument("--report", default="sequoia-x/LATEST.md")
    parser.add_argument("--csv", default="sequoia-x/latest_all_stocks_analysis.csv")
    parser.add_argument("--output", default="daily-stock/sequoia-daily-results.js")
    args = parser.parse_args()

    payload = build_payload(Path(args.report), Path(args.csv))
    write_js(payload, Path(args.output))
    print(f"web results written: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
