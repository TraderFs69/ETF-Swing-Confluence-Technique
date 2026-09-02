from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yaml

from .data import download_history
from .report import send_discord, write_outputs
from .strategy import evaluate_setups, relative_strength_metrics
from .universe import load_universe

ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with (ROOT / "config.yml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def calculate_rs_percentiles(
    universe: pd.DataFrame,
    histories: dict[str, pd.DataFrame],
    benchmarks: dict[str, str],
) -> tuple[dict[str, float], dict[str, float]]:
    excess_returns: dict[str, float] = {}
    percentiles: dict[str, float] = {}

    for row in universe.itertuples(index=False):
        history = histories.get(row.symbol)
        benchmark = histories.get(benchmarks[row.market])
        if history is None or benchmark is None:
            continue
        _, excess_return = relative_strength_metrics(history, benchmark)
        if pd.notna(excess_return):
            excess_returns[row.symbol] = excess_return

    for market in universe["market"].unique():
        symbols = universe.loc[universe["market"] == market, "symbol"]
        values = {symbol: excess_returns[symbol] for symbol in symbols if symbol in excess_returns}
        if not values:
            continue
        series = pd.Series(values, dtype=float)
        market_percentiles = series.rank(method="average", pct=True, ascending=True) * 100
        percentiles.update({symbol: float(value) for symbol, value in market_percentiles.items()})

    return percentiles, excess_returns


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    cfg = load_config()
    enabled_markets = [market.upper() for market in cfg["markets"] if cfg["markets"][market]]
    universe = load_universe(ROOT / "data" / "etfs.csv", enabled_markets)
    benchmarks = {market: str(cfg["benchmarks"][market]).upper() for market in enabled_markets}

    requested_symbols = universe["symbol"].tolist() + list(benchmarks.values())
    histories, download_diagnostics = download_history(requested_symbols, cfg["download"])
    rs_percentiles, excess_returns = calculate_rs_percentiles(universe, histories, benchmarks)

    signals: list[dict] = []
    diagnostics = {
        "universe_size": len(universe),
        "markets": enabled_markets,
        "benchmarks": benchmarks,
        "download": download_diagnostics,
        "relative_strength_available": len(rs_percentiles),
        "missing_history": 0,
        "missing_benchmark": 0,
        "below_rs_percentile": 0,
        "signals": 0,
    }

    minimum_rs = float(cfg["strategy"]["minimum_rs_percentile"])
    for _, meta in universe.iterrows():
        symbol = str(meta["symbol"])
        history = histories.get(symbol)
        benchmark = histories.get(benchmarks[str(meta["market"])])
        if history is None:
            diagnostics["missing_history"] += 1
            continue
        if benchmark is None:
            diagnostics["missing_benchmark"] += 1
            continue

        percentile = rs_percentiles.get(symbol)
        if percentile is None or percentile < minimum_rs:
            diagnostics["below_rs_percentile"] += 1
            continue

        setup_signals = evaluate_setups(meta, history, benchmark, percentile, cfg["strategy"])
        for signal in setup_signals:
            result = signal.to_dict()
            result["excess_return_63"] = round(100 * excess_returns.get(symbol, 0.0), 2)
            signals.append(result)

    diagnostics["signals"] = len(signals)
    top = write_outputs(ROOT, signals, universe, diagnostics, cfg["report"])
    send_discord(top, diagnostics, cfg["discord"])
    logging.info(
        "Terminé — %s signaux, rapport : %s",
        len(signals),
        ROOT / "output" / "rapport_confluence_etf.md",
    )


if __name__ == "__main__":
    main()
