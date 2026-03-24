# CLAUDE.md — Mémoire Projet pour Claude Code

## Qu'est-ce que ce projet ?

**polymarket-btc-bot** est un bot de trading automatisé Python pour les marchés binaires "BTC Up or Down - 5 Minutes" sur Polymarket. Toutes les 5 minutes, Polymarket ouvre un marché : "Est-ce que le prix BTC sera plus haut ou plus bas dans 5 minutes ?" Le bot décide d'acheter un token "Up" ou "Down" (ou de ne rien faire) en comparant le prix BTC temps réel (Binance) avec le prix oracle Chainlink utilisé pour la résolution du marché.

**Objectif business** : win rate ≥ 65% (minimum), cible 70%. Capital de départ 100$ USDC. Les gains sont réinvestis.

**Stratégie Phase 1** : Taker sélectif — n'entre que lorsque le signal est fort (delta ≥ 0.03%, token ≤ 0.60$), en utilisant un modèle GBM analytique pour estimer la probabilité de gain.

## Contexte du code actuel

Le code a été généré par **Devstral 2 via Mistral Vibe CLI**. Le squelette et l'architecture sont corrects, mais il y a des problèmes critiques dans l'implémentation. Claude Code est utilisé pour **reviewer, corriger et consolider** le code.

## Architecture

```
src/
├── config.py              ← Config (.env + constantes) — OK
├── feeds/                 ← Flux WebSocket temps réel — À CORRIGER (picows mal utilisé)
│   ├── binance_ws.py      ← WebSocket Binance btcusdt@aggTrade
│   ├── polymarket_rtds.py ← WebSocket Polymarket RTDS (prix Chainlink)
│   ├── polymarket_clob_ws.py ← WebSocket CLOB (order book)
│   └── feed_manager.py    ← Orchestrateur des 3 flux
├── signal/                ← Calcul du signal — PARTIELLEMENT OK
│   ├── delta.py           ← Delta prix actuel vs ouverture — OK
│   ├── gbm.py             ← Modèle GBM analytique P(Up) — OK
│   ├── volatility.py      ← Volatilité rolling — À CORRIGER (filtrage temporel)
│   ├── indicators.py      ← RSI, EMA — À CORRIGER (boucles Python → numpy)
│   └── scorer.py          ← Score composite → décision — OK
├── strategy/              ← Logique de décision — À CORRIGER (placeholders)
│   ├── taker_selective.py ← Stratégie taker — CRITIQUE: rempli de placeholders
│   ├── kelly.py           ← Kelly conservateur (1/4) — OK
│   └── filters.py         ← Filtres — OK (sauf is_stop_loss_hit)
├── execution/             ← Exécution des ordres — À CORRIGER (API inventée)
│   ├── clob_client.py     ← Wrapper py-clob-client — CRITIQUE: init cassée
│   ├── order_builder.py   ← Construction ordres — CRITIQUE: méthodes inventées
│   ├── slug_resolver.py   ← Slug déterministe — OK
│   └── redeemer.py        ← Auto-redeem — CRITIQUE: méthodes inventées
├── engine/                ← Boucle principale
│   ├── clock.py           ← Sync horloge Unix — OK
│   ├── loop.py            ← Boucle 5 min — À CORRIGER (timing incorrect)
│   └── state.py           ← État bot — À CORRIGER (is_stop_loss_hit)
└── utils/
    ├── logger.py          ← Logging structlog JSON — OK
    ├── metrics.py         ← (non créé)
    └── alerter.py         ← (non créé)
```

## Contraintes techniques ABSOLUES

Ces règles ne sont JAMAIS négociables :

1. **`orjson`** pour tout JSON. Jamais `import json`. `orjson.loads()` / `orjson.dumps()`.
2. **`uvloop`** comme event loop. Le `src/__main__.py` utilise déjà `uvloop.run(main())` — OK.
3. **`@dataclass(slots=True)`** pour toute structure fréquente (Tick, Order, Signal, TradeResult).
4. **`collections.deque(maxlen=N)`** pour les buffers temporels. Jamais `list` avec `pop(0)`.
5. **Numpy vectorisé** pour tout calcul sur séries de prix. Jamais de boucle `for` Python.
6. **`structlog`** JSON pour le logging. Jamais `print()`.
7. **Type hints stricts** sur toute fonction. Compatible `mypy --strict`.
8. **Async** pour toute I/O. Jamais `requests` (bloquant), utiliser `aiohttp`.
9. **Secrets dans `.env`** uniquement. Jamais hardcodés. `.env` est dans `.gitignore`.
10. **Docstrings Google-style** sur toute fonction publique.

## Mécanique du marché Polymarket BTC 5m

- Fenêtres de 5 min, démarrent à chaque multiple de 300s Unix.
- Slug déterministe : `btc-updown-5m-{timestamp}` où `timestamp = now - (now % 300)`.
- L'oracle **Chainlink BTC/USD** (pas Binance) détermine le résultat.
- `prix_fin >= prix_début` → "Up" gagne (token paie 1.00$). Sinon "Down" gagne.
- **Frais taker dynamiques** (fév. 2026) : ~1.56% à p=0.50, ~0.13% aux extrêmes.
- **Ordres maker** : zéro frais + rebates USDC quotidiennes.
- Le SDK `py-clob-client >= 0.34.5` gère le `feeRateBps` automatiquement.
- Profondeur carnet : ~5 000-15 000$ par côté. Minimum 5 tokens par ordre (~2.50$).

## Formules clés

**Delta** : `delta = (prix_actuel - prix_ouverture) / prix_ouverture`
- Skip si `|delta| < 0.0003`

**GBM** : `P(Up) = Φ(delta / (σ_hourly × √(t_remaining / 3600)))`
- Φ = `scipy.stats.norm.cdf`

**Kelly** : `f* = (win_rate × (1/price - 1) - (1 - win_rate)) / (1/price - 1)`
- Bet = `min(f* × 0.25 × bankroll, bankroll × 0.05)`, minimum 2.50$

## Séquence boucle principale (par fenêtre 5 min)

```
T=0s     → Enregistrer prix Chainlink ouverture, calculer slug, résoudre token_ids
T=0-270s → Accumuler ticks Binance, calculer stats rolling
T=270s   → Évaluer delta. Si |delta| < 0.03% → SKIP
T=275s   → Fetch order book. Vérifier best_ask ≤ 0.60$
T=280s   → Calculer P(Up) via GBM. Comparer à best_ask + 0.05
T=285s   → Si edge suffisant → placer ordre
T=295s   → Cancel si non exécuté
T=300s+  → Attendre résolution
T=310s   → Auto-redeem, logger, MAJ bankroll
```

## APIs externes

- **Binance WS** : `wss://stream.binance.com:9443/ws/btcusdt@aggTrade`
- **Polymarket RTDS** : `wss://ws-live-data.polymarket.com`
- **Polymarket CLOB WS** : `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- **Polymarket CLOB REST** : `https://clob.polymarket.com`
- **Polymarket Gamma** : `https://gamma-api.polymarket.com`

## API py-clob-client — Référence correcte

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
from py_clob_client.order_builder.constants import BUY, SELL

# Initialisation
client = ClobClient(
    host="https://clob.polymarket.com",
    key="0x_PRIVATE_KEY",          # clé privée EOA
    chain_id=137,                   # Polygon
    signature_type=0,               # 0=EOA, 1=Magic/proxy
    funder="0x_FUNDER_ADDRESS"      # adresse proxy wallet
)
creds = client.create_or_derive_api_creds()
client.set_api_creds(creds)

# Lecture (synchrone)
book = client.get_order_book(token_id)
price = client.get_price(token_id, side="BUY")
midpoint = client.get_midpoint(token_id)

# Création d'ordre (synchrone)
order_args = OrderArgs(token_id=token_id, price=0.55, size=10.0, side=BUY)
signed = client.create_order(order_args)
resp = client.post_order(signed, OrderType.GTC)

# Annulation (synchrone)
client.cancel(order_id)
client.cancel_all()

# IMPORTANT : ces méthodes sont SYNCHRONES.
# En contexte async, wrapper avec asyncio.to_thread() :
book = await asyncio.to_thread(client.get_order_book, token_id)
resp = await asyncio.to_thread(client.post_order, signed, OrderType.GTC)
```

## Dépendances

```
uvloop>=0.22.0, orjson>=3.10.0, aiohttp>=3.9.0, py-clob-client>=0.34.5,
numpy>=1.26.0, scipy>=1.12.0, structlog>=24.0.0, python-dotenv>=1.0.0, web3>=7.0.0
```

## Commandes utiles

```bash
# Lancer les tests
pytest tests/ -v

# Lint
ruff check src/

# Type check
mypy --strict src/

# Lancer le bot en dry-run
python -m src --mode dry-run

# Setup CLI
python -m setup_cli
```
