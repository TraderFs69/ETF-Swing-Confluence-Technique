# ETF Swing — Confluence technique — Trading en Action

Scanner quotidien d'ETF canadiens et américains utilisant les prix ajustés de Yahoo Finance.

Le programme classe séparément deux configurations :

1. **Repli haussier** : retour contrôlé vers EMA20/EMA50 suivi d'une reprise.
2. **Cassure momentum** : clôture au-dessus du sommet des 20 séances précédentes.

## Score de confluence sur 100

| Bloc | Points |
|---|---:|
| Tendance hebdomadaire EMA10/EMA30 | 15 |
| Tendance quotidienne EMA20/50/200 | 15 |
| ADX et DMI | 10 |
| Force relative contre XIC ou SPY | 15 |
| RSI | 10 |
| MACD | 10 |
| Bandes de Bollinger | 5 |
| Heikin-Ashi | 5 |
| Structure du prix | 10 |
| Volume relatif | 5 |

Le RSI, le MACD et l'ADX ont des rôles différents afin d'éviter de donner plusieurs fois des points au même type d'information. L'ATR sert à calculer le stop et les objectifs 2R/3R; il ne prédit pas la direction.

## Installation locale

Python 3.11 ou plus récent est recommandé.

Windows :

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python -m scanner.main

macOS ou Linux :

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m scanner.main

## Installation dans GitHub

1. Téléverser tout le contenu du projet à la racine du dépôt.
2. Vérifier que le fichier se trouve dans **.github/workflows/scan.yml**.
3. Ouvrir **Settings → Secrets and variables → Actions**.
4. Créer le secret **DISCORD_WEBHOOK_URL**.
5. Ouvrir **Actions → ETF Swing - Confluence technique**.
6. Cliquer sur **Run workflow**.

Le scan automatique est prévu du lundi au vendredi à **22 h 30 UTC**, après la clôture nord-américaine. GitHub utilise l'heure UTC; le passage à l'heure d'hiver peut donc décaler l'heure locale d'une heure.

## Configuration

Tous les réglages se trouvent dans **config.yml**.

Pour analyser seulement le Canada :

    markets:
      CA: true
      US: false

Paramètres importants :

- **pullback_minimum_score** : score minimal des replis;
- **breakout_minimum_score** : score minimal des cassures;
- **minimum_rs_percentile** : 70 conserve les 30 % les plus forts;
- **minimum_average_dollar_volume** : filtre de négociabilité, sans points automatiques;
- **maximum_risk_pct** : rejette les configurations dont le stop est trop éloigné;
- **maximum_per_category** : évite un Top 10 dominé par une seule thématique.

L'univers de 165 ETF se trouve dans **data/etfs.csv**. Il peut être modifié avec les symboles Yahoo Finance.

## Résultats

Chaque exécution produit :

- **output/tous_les_signaux_confluence.csv**;
- **output/top_replis_haussiers.csv**;
- **output/top_cassures_momentum.csv**;
- **output/rapport_confluence_etf.md**;
- **output/univers_etf_utilise.csv**;
- **output/diagnostics.json**.

Les résultats sont publiés dans deux sections Discord et conservés pendant 30 jours comme artifact GitHub.

## Avertissement

Le scanner est un outil d'aide à l'analyse et non un système d'exécution d'ordres. Les scores techniques, stops et objectifs sont indicatifs et ne constituent ni une recommandation personnalisée ni une garantie de rendement. Yahoo Finance est une source pratique, mais non un flux officiel de courtage.
