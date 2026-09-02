from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

LOGGER = logging.getLogger(__name__)

COLUMNS = [
    "symbol", "name", "market", "category", "date", "setup", "score", "close",
    "trigger", "rs_percentile", "rsi", "adx", "macd_histogram", "bollinger_pctb",
    "relative_volume", "average_dollar_volume", "atr", "stop", "target_2r",
    "target_3r", "risk_pct", "reasons", "excess_return_63",
]


def select_diversified(frame: pd.DataFrame, top_n: int, max_per_category: int) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    selected: list[int] = []
    category_counts: dict[str, int] = {}
    for index, row in frame.iterrows():
        category = str(row["category"])
        if category_counts.get(category, 0) >= max_per_category:
            continue
        selected.append(index)
        category_counts[category] = category_counts.get(category, 0) + 1
        if len(selected) >= top_n:
            break
    return frame.loc[selected].reset_index(drop=True)


def _top_for_setup(frame: pd.DataFrame, setup: str, cfg: dict) -> pd.DataFrame:
    subset = frame.loc[frame["setup"] == setup].copy()
    return select_diversified(
        subset,
        top_n=int(cfg["top_n_per_setup"]),
        max_per_category=int(cfg["maximum_per_category"]),
    )


def _markdown_table(lines: list[str], title: str, frame: pd.DataFrame) -> None:
    lines.extend(["", f"## {title}", ""])
    if frame.empty:
        lines.append("Aucun signal admissible.")
        return
    lines.extend([
        "| Rang | ETF | Marché | Catégorie | Score | Prix | Force rel. | RSI | ADX | Stop | Cible 2R |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for rank, row in enumerate(frame.itertuples(index=False), 1):
        currency = "$ CA" if row.market == "CA" else "$ US"
        lines.append(
            f"| {rank} | {row.symbol} | {row.market} | {row.category} | {row.score}/100 | "
            f"{row.close:.2f} {currency} | {row.rs_percentile:.0f}e | {row.rsi:.1f} | "
            f"{row.adx:.1f} | {row.stop:.2f} | {row.target_2r:.2f} |"
        )
    lines.extend(["", "### Confluences", ""])
    for row in frame.itertuples(index=False):
        lines.append(f"- **{row.symbol} — {row.score}/100 — {row.trigger} :** {row.reasons}")


def write_outputs(
    root: Path,
    signals: list[dict],
    universe: pd.DataFrame,
    diagnostics: dict,
    cfg: dict,
) -> dict[str, pd.DataFrame]:
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(signals, columns=COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(
            ["setup", "score", "rs_percentile", "relative_volume", "symbol"],
            ascending=[True, False, False, False, True],
        ).reset_index(drop=True)

    tops = {
        "REPLI HAUSSIER": _top_for_setup(frame, "REPLI HAUSSIER", cfg),
        "CASSURE MOMENTUM": _top_for_setup(frame, "CASSURE MOMENTUM", cfg),
    }

    frame.to_csv(output / "tous_les_signaux_confluence.csv", index=False)
    tops["REPLI HAUSSIER"].to_csv(output / "top_replis_haussiers.csv", index=False)
    tops["CASSURE MOMENTUM"].to_csv(output / "top_cassures_momentum.csv", index=False)
    universe.to_csv(output / "univers_etf_utilise.csv", index=False)
    (output / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    now = datetime.now(ZoneInfo("America/Toronto"))
    lines = [
        "# ETF Swing — Confluence technique — Trading en Action",
        "",
        f"Généré le **{now:%Y-%m-%d à %H:%M} HE** avec une bougie quotidienne terminée.",
        f"Univers actif : **{len(universe)} ETF**. Données valides : **{diagnostics['download']['downloaded']}**. Signaux : **{len(frame)}**.",
    ]
    _markdown_table(lines, "Replis haussiers", tops["REPLI HAUSSIER"])
    _markdown_table(lines, "Cassures momentum", tops["CASSURE MOMENTUM"])
    lines.extend([
        "",
        "> Les scores classent des configurations techniques. Ils ne constituent ni une recommandation ni une garantie de rendement.",
    ])
    (output / "rapport_confluence_etf.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tops


def _discord_description(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "Aucun signal admissible aujourd'hui."
    blocks: list[str] = []
    for rank, row in enumerate(frame.head(10).itertuples(index=False), 1):
        currency = "CA" if row.market == "CA" else "US"
        blocks.append(
            f"**{rank}. {row.symbol} — {row.score}/100** · {row.category}\n"
            f"Prix {row.close:.2f} $ {currency} | FR {row.rs_percentile:.0f}e | "
            f"RSI {row.rsi:.1f} | ADX {row.adx:.1f}\n"
            f"{row.trigger} | Stop {row.stop:.2f} | 2R {row.target_2r:.2f} | 3R {row.target_3r:.2f}"
        )
    return "\n\n".join(blocks)


def send_discord(tops: dict[str, pd.DataFrame], diagnostics: dict, cfg: dict) -> None:
    if not cfg.get("enabled", False):
        return
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        LOGGER.warning("DISCORD_WEBHOOK_URL absent : rapport créé sans publication Discord.")
        return

    footer = (
        f"Couverture Yahoo {diagnostics['download']['coverage_pct']} % · "
        "Bougie quotidienne terminée"
    )
    payload = {
        "username": cfg.get("username", "Trading en Action"),
        "embeds": [
            {
                "title": "🟢 ETF — Replis haussiers",
                "description": _discord_description(tops["REPLI HAUSSIER"])[:4000],
                "color": 0x2ECC71,
                "footer": {"text": footer},
            },
            {
                "title": "🚀 ETF — Cassures momentum",
                "description": _discord_description(tops["CASSURE MOMENTUM"])[:4000],
                "color": 0xD4AF37,
                "footer": {"text": footer},
            },
        ],
    }

    for attempt in range(1, 4):
        try:
            response = requests.post(webhook, json=payload, timeout=20)
            response.raise_for_status()
            return
        except requests.RequestException as exc:
            LOGGER.warning("Discord, tentative %s/3 : %s", attempt, exc)
            if attempt < 3:
                time.sleep(2 * attempt)
    LOGGER.error("Impossible de publier le rapport sur Discord après trois tentatives.")
