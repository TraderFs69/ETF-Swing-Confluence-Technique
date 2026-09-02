from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"symbol", "name", "market", "category", "enabled"}


def load_universe(path: Path, enabled_markets: list[str]) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans {path}: {sorted(missing)}")

    frame = frame.copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["market"] = frame["market"].astype(str).str.strip().str.upper()
    frame["category"] = frame["category"].astype(str).str.strip()
    enabled = frame["enabled"].astype(str).str.lower().isin({"true", "1", "yes", "oui"})
    frame = frame[enabled & frame["market"].isin([market.upper() for market in enabled_markets])]
    frame = frame.drop_duplicates("symbol").reset_index(drop=True)
    if frame.empty:
        raise RuntimeError("L'univers ETF est vide après l'application des filtres.")
    return frame
