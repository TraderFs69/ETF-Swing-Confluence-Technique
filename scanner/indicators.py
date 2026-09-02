from __future__ import annotations

import numpy as np
import pandas as pd


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + relative_strength)
    return rsi.where(average_loss != 0, 100.0)


def atr_wilder(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def adx_dmi(frame: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    up_move = frame["High"].diff()
    down_move = -frame["Low"].diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=frame.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=frame.index)
    atr = atr_wilder(frame, period)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame(
        {
            "ADX": dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean(),
            "PlusDI": plus_di,
            "MinusDI": minus_di,
        },
        index=frame.index,
    )


def heikin_ashi(frame: pd.DataFrame) -> pd.DataFrame:
    ha = pd.DataFrame(index=frame.index)
    ha["Close"] = (frame["Open"] + frame["High"] + frame["Low"] + frame["Close"]) / 4
    ha_open = np.zeros(len(frame), dtype=float)
    if len(frame):
        ha_open[0] = (float(frame["Open"].iloc[0]) + float(frame["Close"].iloc[0])) / 2
        for index in range(1, len(frame)):
            ha_open[index] = (ha_open[index - 1] + float(ha["Close"].iloc[index - 1])) / 2
    ha["Open"] = ha_open
    ha["Green"] = ha["Close"] > ha["Open"]
    ha["Body"] = (ha["Close"] - ha["Open"]).abs()
    return ha


def weekly_trend(history: pd.DataFrame) -> tuple[bool, float, float]:
    """Utilise seulement la dernière semaine terminée (vendredi inclus)."""
    weekly = history.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["Close"])
    if not weekly.empty and weekly.index[-1].date() > pd.Timestamp(history.index[-1]).date():
        weekly = weekly.iloc[:-1]
    if len(weekly) < 35:
        return False, float("nan"), float("nan")
    ema10 = weekly["Close"].ewm(span=10, adjust=False).mean()
    ema30 = weekly["Close"].ewm(span=30, adjust=False).mean()
    strong = bool(
        weekly["Close"].iloc[-1] > ema10.iloc[-1] > ema30.iloc[-1]
        and ema10.iloc[-1] > ema10.iloc[-4]
    )
    return strong, float(ema10.iloc[-1]), float(ema30.iloc[-1])


def add_indicators(frame: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = frame.copy()
    for period in (20, 50, 200):
        out[f"EMA{period}"] = out["Close"].ewm(span=period, adjust=False).mean()

    out["RSI"] = rsi_wilder(out["Close"], int(cfg["rsi_period"]))
    out["ATR"] = atr_wilder(out, int(cfg["atr_period"]))

    macd_fast = out["Close"].ewm(span=int(cfg["macd_fast"]), adjust=False).mean()
    macd_slow = out["Close"].ewm(span=int(cfg["macd_slow"]), adjust=False).mean()
    out["MACD"] = macd_fast - macd_slow
    out["MACDSignal"] = out["MACD"].ewm(span=int(cfg["macd_signal"]), adjust=False).mean()
    out["MACDHistogram"] = out["MACD"] - out["MACDSignal"]

    dmi = adx_dmi(out, int(cfg["adx_period"]))
    out[["ADX", "PlusDI", "MinusDI"]] = dmi[["ADX", "PlusDI", "MinusDI"]]

    bb_period = int(cfg["bollinger_period"])
    bb_mid = out["Close"].rolling(bb_period).mean()
    bb_std = out["Close"].rolling(bb_period).std(ddof=0)
    out["BBMiddle"] = bb_mid
    out["BBUpper"] = bb_mid + float(cfg["bollinger_std"]) * bb_std
    out["BBLower"] = bb_mid - float(cfg["bollinger_std"]) * bb_std
    out["BollingerPctB"] = (
        (out["Close"] - out["BBLower"])
        / (out["BBUpper"] - out["BBLower"]).replace(0, np.nan)
    )

    volume_period = int(cfg["volume_average_period"])
    out["VolumeAverage"] = out["Volume"].rolling(volume_period).mean()
    out["DollarVolumeAverage"] = (
        (out["Close"] * out["Volume"]).rolling(volume_period).mean()
    )
    out["Previous20High"] = out["High"].shift(1).rolling(20).max()
    out["CloseLocation"] = (
        (out["Close"] - out["Low"])
        / (out["High"] - out["Low"]).replace(0, np.nan)
    )

    ha = heikin_ashi(out)
    out["HAGreen"] = ha["Green"]
    out["HABody"] = ha["Body"]
    return out
