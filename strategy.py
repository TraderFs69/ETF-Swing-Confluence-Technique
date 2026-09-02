from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .indicators import add_indicators, weekly_trend


@dataclass
class Signal:
    symbol: str
    name: str
    market: str
    category: str
    date: str
    setup: str
    score: int
    close: float
    trigger: str
    rs_percentile: float
    rsi: float
    adx: float
    macd_histogram: float
    bollinger_pctb: float
    relative_volume: float
    average_dollar_volume: float
    atr: float
    stop: float
    target_2r: float
    target_3r: float
    risk_pct: float
    reasons: str

    def to_dict(self) -> dict:
        return asdict(self)


def _confirmed_higher_low(values: pd.Series, lookback: int = 50) -> bool:
    recent = values.tail(lookback).reset_index(drop=True)
    pivots: list[float] = []
    for index in range(2, len(recent) - 2):
        window = recent.iloc[index - 2 : index + 3]
        if recent.iloc[index] == window.min() and int((window == recent.iloc[index]).sum()) == 1:
            pivots.append(float(recent.iloc[index]))
    return len(pivots) >= 2 and pivots[-1] > pivots[-2]


def relative_strength_metrics(history: pd.DataFrame, benchmark: pd.DataFrame) -> tuple[bool, float]:
    aligned = pd.concat(
        [history["Close"].rename("ETF"), benchmark["Close"].rename("Benchmark")],
        axis=1,
        join="inner",
    ).dropna()
    if len(aligned) < 70:
        return False, float("nan")
    ratio = aligned["ETF"] / aligned["Benchmark"]
    ratio_ema50 = ratio.ewm(span=50, adjust=False).mean()
    strong = bool(ratio.iloc[-1] > ratio_ema50.iloc[-1] and ratio.iloc[-1] > ratio.iloc[-10])
    excess_return_63 = float(
        aligned["ETF"].pct_change(63).iloc[-1]
        - aligned["Benchmark"].pct_change(63).iloc[-1]
    )
    return strong, excess_return_63


def _ema_rebounds(frame: pd.DataFrame, cfg: dict) -> list[str]:
    recent = frame.tail(int(cfg["pullback_lookback"]) + 1).iloc[:-1]
    tolerance = float(cfg["ema_touch_atr_tolerance"])
    current = frame.iloc[-1]
    rebounds: list[str] = []
    for period in (20, 50):
        ema = recent[f"EMA{period}"]
        touched = (
            ((recent["Low"] - ema).abs() <= recent["ATR"] * tolerance)
            | ((recent["Low"] <= ema) & (recent["High"] >= ema))
        ).any()
        if touched and current["Close"] > current[f"EMA{period}"]:
            rebounds.append(f"EMA{period}")
    return rebounds


def _macd_improving(frame: pd.DataFrame) -> bool:
    histogram = frame["MACDHistogram"]
    recent_cross = (
        (frame["MACD"].tail(4) > frame["MACDSignal"].tail(4))
        & (frame["MACD"].tail(4).shift(1) <= frame["MACDSignal"].tail(4).shift(1))
    ).any()
    rising_three = bool(histogram.iloc[-1] > histogram.iloc[-2] > histogram.iloc[-3])
    return bool(histogram.iloc[-1] > histogram.iloc[-2] and (histogram.iloc[-1] > 0 or recent_cross or rising_three))


def _make_signal(
    meta: pd.Series,
    frame: pd.DataFrame,
    setup: str,
    score: int,
    trigger: str,
    rs_percentile: float,
    reasons: list[str],
    stop_reference: float,
    cfg: dict,
) -> Signal | None:
    current = frame.iloc[-1]
    close = float(current["Close"])
    atr = float(current["ATR"])
    stop = min(stop_reference - 0.10 * atr, close - float(cfg["stop_atr"]) * atr)
    risk = close - stop
    risk_pct = 100 * risk / close
    if risk <= 0 or risk_pct > float(cfg["maximum_risk_pct"]):
        return None

    relative_volume = (
        float(current["Volume"] / current["VolumeAverage"])
        if current["VolumeAverage"] > 0
        else 0.0
    )
    return Signal(
        symbol=str(meta["symbol"]),
        name=str(meta["name"]),
        market=str(meta["market"]),
        category=str(meta["category"]),
        date=str(pd.Timestamp(frame.index[-1]).date()),
        setup=setup,
        score=min(int(score), 100),
        close=round(close, 4),
        trigger=trigger,
        rs_percentile=round(rs_percentile, 1),
        rsi=round(float(current["RSI"]), 1),
        adx=round(float(current["ADX"]), 1),
        macd_histogram=round(float(current["MACDHistogram"]), 4),
        bollinger_pctb=round(float(current["BollingerPctB"]), 2),
        relative_volume=round(relative_volume, 2),
        average_dollar_volume=round(float(current["DollarVolumeAverage"])),
        atr=round(atr, 4),
        stop=round(stop, 4),
        target_2r=round(close + 2 * risk, 4),
        target_3r=round(close + 3 * risk, 4),
        risk_pct=round(risk_pct, 2),
        reasons="; ".join(reasons),
    )


def evaluate_setups(
    meta: pd.Series,
    history: pd.DataFrame,
    benchmark: pd.DataFrame,
    rs_percentile: float,
    cfg: dict,
) -> list[Signal]:
    if len(history) < int(cfg["minimum_history_sessions"]):
        return []

    required = [
        "EMA20", "EMA50", "EMA200", "RSI", "ATR", "ADX", "MACDHistogram",
        "BBMiddle", "BollingerPctB", "DollarVolumeAverage", "Previous20High",
    ]
    frame = add_indicators(history, cfg).dropna(subset=required)
    if len(frame) < 30:
        return []

    current = frame.iloc[-1]
    previous = frame.iloc[-2]
    close = float(current["Close"])
    atr = float(current["ATR"])
    market = str(meta["market"])
    average_dollar_volume = float(current["DollarVolumeAverage"])

    if close < float(cfg["minimum_price"]):
        return []
    if average_dollar_volume < float(cfg["minimum_average_dollar_volume"][market]):
        return []
    if atr <= 0 or not np.isfinite([close, atr, rs_percentile]).all():
        return []
    if close <= float(current["EMA200"]):
        return []

    rs_strong, _ = relative_strength_metrics(history, benchmark)
    if rs_percentile < float(cfg["minimum_rs_percentile"]):
        return []

    weekly_strong, _, _ = weekly_trend(history)
    adx_positive = bool(
        current["ADX"] >= float(cfg["minimum_adx"])
        and current["PlusDI"] > current["MinusDI"]
    )
    macd_positive = _macd_improving(frame)
    relative_volume = (
        float(current["Volume"] / current["VolumeAverage"])
        if current["VolumeAverage"] > 0
        else 0.0
    )
    volume_positive = relative_volume >= float(cfg["minimum_relative_volume_bonus"])
    ha_green = bool(current["HAGreen"])
    ha_turn = ha_green and not bool(previous["HAGreen"])
    higher_low = _confirmed_higher_low(frame["Low"])
    price_confirmation = close > float(previous["High"])
    rebounds = _ema_rebounds(frame, cfg)
    results: list[Signal] = []

    # Configuration 1 : repli dans une tendance haussière.
    pullback_extension = max(0.0, (close - float(current["EMA20"])) / atr)
    if rebounds and pullback_extension <= float(cfg["pullback_maximum_extension_atr"]):
        score = 0
        reasons: list[str] = []
        if weekly_strong:
            score += 15
            reasons.append("hebdo : prix > EMA10 > EMA30")
        if close > current["EMA50"] > current["EMA200"]:
            score += 15
            reasons.append("daily : prix > EMA50 > EMA200")
        if adx_positive:
            score += 10
            reasons.append(f"ADX/DMI haussier ({current['ADX']:.1f})")
        if rs_strong and rs_percentile >= float(cfg["minimum_rs_percentile"]):
            score += 15
            reasons.append(f"force relative {rs_percentile:.0f}e percentile")
        pullback_rsi = (
            float(cfg["pullback_rsi_minimum"]) <= current["RSI"] <= float(cfg["pullback_rsi_maximum"])
            and current["RSI"] > previous["RSI"]
        )
        if pullback_rsi:
            score += 10
            reasons.append(f"RSI en reprise ({current['RSI']:.1f})")
        if macd_positive:
            score += 10
            reasons.append("MACD en accélération")
        recent_pctb = frame["BollingerPctB"].tail(int(cfg["pullback_lookback"]) + 1).iloc[:-1]
        bollinger_rebound = bool(
            recent_pctb.min() <= float(cfg["pullback_bollinger_maximum"])
            and current["BollingerPctB"] > previous["BollingerPctB"]
        )
        if bollinger_rebound:
            score += 5
            reasons.append("rebond Bollinger")
        if ha_turn:
            score += 5
            reasons.append("Heikin-Ashi rouge vers vert")
        if higher_low:
            score += 5
            reasons.append("Higher Low")
        if price_confirmation:
            score += 5
            reasons.append("clôture > sommet précédent")
        if volume_positive:
            score += 5
            reasons.append(f"volume relatif {relative_volume:.2f}x")

        if score >= int(cfg["pullback_minimum_score"]):
            signal = _make_signal(
                meta, frame, "REPLI HAUSSIER", score,
                "Rebond " + "/".join(rebounds), rs_percentile, reasons,
                float(frame["Low"].tail(10).min()), cfg,
            )
            if signal:
                results.append(signal)

    # Configuration 2 : cassure de momentum sur 20 séances.
    breakout_level = float(current["Previous20High"])
    breakout_extension = max(0.0, (close - float(current["EMA20"])) / atr)
    is_breakout = close > breakout_level and float(current["CloseLocation"]) >= float(cfg["breakout_minimum_close_location"])
    if is_breakout and breakout_extension <= float(cfg["breakout_maximum_extension_atr"]):
        score = 0
        reasons = []
        if weekly_strong:
            score += 15
            reasons.append("hebdo : prix > EMA10 > EMA30")
        if close > current["EMA20"] > current["EMA50"] > current["EMA200"]:
            score += 15
            reasons.append("daily : EMA20 > EMA50 > EMA200")
        if adx_positive:
            score += 10
            reasons.append(f"ADX/DMI haussier ({current['ADX']:.1f})")
        if rs_strong and rs_percentile >= float(cfg["minimum_rs_percentile"]):
            score += 15
            reasons.append(f"force relative {rs_percentile:.0f}e percentile")
        breakout_rsi = (
            float(cfg["breakout_rsi_minimum"]) <= current["RSI"] <= float(cfg["breakout_rsi_maximum"])
            and current["RSI"] >= previous["RSI"]
        )
        if breakout_rsi:
            score += 10
            reasons.append(f"RSI momentum ({current['RSI']:.1f})")
        if macd_positive:
            score += 10
            reasons.append("MACD en accélération")
        if float(cfg["breakout_bollinger_minimum"]) <= current["BollingerPctB"] <= float(cfg["breakout_bollinger_maximum"]):
            score += 5
            reasons.append("momentum Bollinger contrôlé")
        if ha_green and current["HABody"] >= previous["HABody"]:
            score += 5
            reasons.append("Heikin-Ashi verte en expansion")
        score += 10
        reasons.append("cassure du sommet 20 jours")
        if volume_positive:
            score += 5
            reasons.append(f"volume relatif {relative_volume:.2f}x")

        if score >= int(cfg["breakout_minimum_score"]):
            signal = _make_signal(
                meta, frame, "CASSURE MOMENTUM", score,
                f"Cassure 20 j : {breakout_level:.2f}", rs_percentile, reasons,
                breakout_level, cfg,
            )
            if signal:
                results.append(signal)

    return results
