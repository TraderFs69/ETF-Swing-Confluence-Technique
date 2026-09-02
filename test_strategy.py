import pandas as pd

from scanner.report import select_diversified
from scanner.strategy import relative_strength_metrics


def test_relative_strength_detects_outperformance():
    index = pd.date_range("2025-01-01", periods=100, freq="B")
    etf = pd.DataFrame({"Close": [100 + index * 1.0 for index in range(100)]}, index=index)
    benchmark = pd.DataFrame({"Close": [100 + index * 0.2 for index in range(100)]}, index=index)
    strong, excess = relative_strength_metrics(etf, benchmark)
    assert strong
    assert excess > 0


def test_diversified_selection_limits_each_category():
    frame = pd.DataFrame([
        {"symbol": "A", "category": "Tech", "score": 95},
        {"symbol": "B", "category": "Tech", "score": 94},
        {"symbol": "C", "category": "Tech", "score": 93},
        {"symbol": "D", "category": "Energy", "score": 92},
    ])
    selected = select_diversified(frame, top_n=4, max_per_category=2)
    assert selected["symbol"].tolist() == ["A", "B", "D"]
