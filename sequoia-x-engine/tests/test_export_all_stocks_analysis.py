from pathlib import Path

from scripts.export_all_stocks_analysis import load_strategy_results_from_report


def test_load_strategy_results_from_report_reads_top_five_heading(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        "\n".join(
            [
                "# Sequoia-X 选股日报",
                "- MaVolumeStrategy：候选 6 只，当日数据 5 只，展示 Top 5",
                "  000006, 000005, 000004, 000003, 000002",
                "  - 000006 示例股份｜理由：放量金叉。",
            ]
        ),
        encoding="utf-8",
    )

    results = load_strategy_results_from_report(report)

    assert results["MaVolumeStrategy"] == {"000006", "000005", "000004", "000003", "000002"}
