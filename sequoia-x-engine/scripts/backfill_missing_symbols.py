"""Parallel resumable backfill for missing A-share symbols in the local SQLite DB."""

from __future__ import annotations

import argparse
import os
import socket
import sqlite3
from datetime import date
from multiprocessing import Pool
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import pandas as pd
from dotenv import load_dotenv

from sequoia_x.core.config import get_settings
from sequoia_x.data.engine import _bs_fetch_batch, DataEngine


def fetch_batch_with_timeout(tasks: list[tuple[str, str, str, str]]) -> list[list[str]]:
    socket.setdefaulttimeout(20.0)
    return _bs_fetch_batch(tasks)


def missing_symbols(all_symbols: Sequence[str], local_symbols: set[str]) -> list[str]:
    return [symbol for symbol in all_symbols if symbol not in local_symbols]


def chunked(items: Sequence[str], size: int) -> Iterator[list[str]]:
    if size <= 0:
        raise ValueError("size must be positive")
    for idx in range(0, len(items), size):
        yield list(items[idx : idx + size])


def local_symbols(db_path: str) -> set[str]:
    if not Path(db_path).exists():
        return set()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT symbol FROM stock_daily").fetchall()
    return {row[0] for row in rows}


def insert_rows(db_path: str, rows: list[list[str]]) -> int:
    if not rows:
        return 0

    df = pd.DataFrame(
        rows,
        columns=["symbol", "date", "open", "high", "low", "close", "volume", "turnover"],
    )
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    df = df[df["volume"] > 0]
    if df.empty:
        return 0

    with sqlite3.connect(db_path) as conn:
        df.to_sql("stock_daily", conn, if_exists="append", index=False, method="multi", chunksize=500)
        conn.commit()
    return len(df)


def backfill_missing(
    *,
    batch_size: int = 240,
    workers: int = 8,
    max_batches: int | None = None,
) -> None:
    os.environ.setdefault(
        "FEISHU_WEBHOOK_URL",
        "https://open.feishu.cn/open-apis/bot/v2/hook/codex-disabled",
    )
    load_dotenv()
    settings = get_settings()
    engine = DataEngine(settings)
    all_symbols = engine.get_all_symbols()
    remaining = missing_symbols(all_symbols, local_symbols(settings.db_path))
    print(f"all_symbols={len(all_symbols)} local_symbols={len(all_symbols) - len(remaining)} missing={len(remaining)}")

    end_date = date.today().strftime("%Y-%m-%d")
    processed_batches = 0
    total_inserted = 0
    for batch_symbols in chunked(remaining, batch_size):
        if max_batches is not None and processed_batches >= max_batches:
            break

        tasks = [
            (symbol, engine._to_baostock_code(symbol), settings.start_date, end_date)
            for symbol in batch_symbols
        ]
        n_workers = min(workers, len(tasks))
        task_chunks = [tasks[idx::n_workers] for idx in range(n_workers)]
        print(
            f"batch={processed_batches + 1} symbols={len(batch_symbols)} "
            f"range={batch_symbols[0]}..{batch_symbols[-1]}"
        )
        with Pool(n_workers) as pool:
            batch_results = pool.map(fetch_batch_with_timeout, task_chunks)

        rows: list[list[str]] = []
        for result in batch_results:
            rows.extend(result)
        inserted = insert_rows(settings.db_path, rows)
        total_inserted += inserted
        processed_batches += 1
        now_local = len(local_symbols(settings.db_path))
        print(f"batch_done={processed_batches} inserted_rows={inserted} local_symbols={now_local}")

    print(f"done batches={processed_batches} inserted_rows={total_inserted}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing symbols into the Sequoia-X database.")
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-batches", type=int, default=None)
    args = parser.parse_args()
    backfill_missing(batch_size=args.batch_size, workers=args.workers, max_batches=args.max_batches)


if __name__ == "__main__":
    main()
