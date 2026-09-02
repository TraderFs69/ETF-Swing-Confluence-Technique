import numpy as np
import pandas as pd

from scanner.indicators import adx_dmi, atr_wilder, heikin_ashi, rsi_wilder, weekly_trend


def test_rsi_of_strong_uptrend_is_high():
    close = pd.Series(np.arange(1.0, 60.0))
    assert rsi_wilder(close, 14).iloc[-1] == 100.0


def test_atr_is_positive():
    close = pd.Series(np.linspace(10, 20, 60))
    frame = pd.DataFrame({
        "Open": close - 0.1,
        "High": close + 0.5,
        "Low": close - 0.5,
        "Close": close,
    })
    assert atr_wilder(frame, 14).iloc[-1] > 0


def test_heikin_ashi_returns_one_row_per_bar():
    frame = pd.DataFrame({
        "Open": [10, 11, 12],
        "High": [12, 13, 14],
        "Low": [9, 10, 11],
        "Close": [11, 12, 13],
    })
    result = heikin_ashi(frame)
    assert len(result) == len(frame)
    assert {"Open", "Close", "Green"}.issubset(result.columns)


def test_adx_dmi_recognizes_a_clean_uptrend():
    close = pd.Series(np.linspace(20, 60, 120))
    frame = pd.DataFrame({
        "Open": close - 0.1,
        "High": close + 0.4,
        "Low": close - 0.4,
        "Close": close,
    })
    result = adx_dmi(frame, 14).dropna()
    assert result["ADX"].iloc[-1] > 20
    assert result["PlusDI"].iloc[-1] > result["MinusDI"].iloc[-1]


def test_weekly_trend_uses_ema10_above_ema30():
    index = pd.date_range("2024-01-01", periods=420, freq="B")
    close = pd.Series(np.linspace(40, 100, len(index)), index=index)
    frame = pd.DataFrame({
        "Open": close - 0.1,
        "High": close + 0.5,
        "Low": close - 0.5,
        "Close": close,
        "Volume": 1_000_000,
    }, index=index)
    strong, ema10, ema30 = weekly_trend(frame)
    assert strong
    assert ema10 > ema30
