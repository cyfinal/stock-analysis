import unittest

from scripts.backfill_missing_symbols import missing_symbols, chunked


class BackfillMissingSymbolsTests(unittest.TestCase):
    def test_missing_symbols_preserves_market_order(self) -> None:
        all_symbols = ["000001", "000002", "600000", "600001"]
        local_symbols = {"000002", "600001"}

        self.assertEqual(missing_symbols(all_symbols, local_symbols), ["000001", "600000"])

    def test_chunked_splits_batches(self) -> None:
        self.assertEqual(
            list(chunked(["a", "b", "c", "d", "e"], 2)),
            [["a", "b"], ["c", "d"], ["e"]],
        )


if __name__ == "__main__":
    unittest.main()
