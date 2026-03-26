# CLAUDE.md — Mémoire Projet pour Claude Code

> Dernière mise à jour : **26 mars 2026**
> Sources : conversations "Planification", "Analyse logs dry-run #1", "Correction feeds + vérification MCP", "Fix PING + re-subscription WS"

---

## 1. Qu'est-ce que ce projet ?

**polymarket-btc-bot** est un bot de trading automatisé Python pour les marchés binaires "BTC Up or Down - 5 Minutes" sur Polymarket. Toutes les 5 minutes, Polymarket ouvre un marché : "Le prix BTC sera-t-il plus haut ou plus bas dans 5 minutes ?" Le bot décide d'acheter un token "Up" ou "Down" (ou de ne rien faire) en comparant le prix BTC temps réel (Binance) avec le prix oracle Chainlink utilisé pour la résolution.

**Objectif business** : win rate ≥ 65% (minimum), cible 70%. Capital : 100 $ USDC. Gains réinvestis via Kelly conservateur (1/4).

**Stratégie Phase 1** : Taker sélectif — entre uniquement quand le signal est fort (delta ≥ 0.03%, token ≤ 0.60$), via modèle GBM analytique pour estimer P(Up).

**Auteur** : Clément Bondaz-Sanson — Montréal, Québec.

---

## 2. Historique du projet

### Genèse (mars 2026)

Approche TFT (Temporal Fusion Transformer) basée sur données on-chain massives (UTXO, Glassnode, mempool) abandonnée : sur-engineerée pour 5 minutes, coût infra > capital de trading.

### Architecture actuelle (23 mars 2026)

Pivot vers un bot taker basé sur trois signaux simples :
- Delta prix Binance vs Chainlink (T=0 → T=~280s)
- Volatilité rolling BTC (GBM)
- RSI + EMA spread sur les 600 derniers ticks

Code généré par **Devstral 2 via Mistral Vibe CLI**, reviewé et corrigé par **Claude Code**.

### Dry-run #1 (25 mars 2026, 10h42m)

- Pod RunPod A40, Montréal (IP US)
- **Résultats** : 129 fenêtres évaluées, **128 SKIP, 0 trade**
- **Feeds** : 3 connectés (Binance ✅, RTDS ✅, CLOB WS connecté mais non fonctionnel ❌)
- **Slugs** : résolus via Gamma API ✅ — **Prix Chainlink** : reçus ✅
- **Bug #1** : `polymarket_clob: false` sur 100% des health checks malgré 323 482 messages reçus — subscribe CLOB incorrect
- **Bug #2** : `calc_rolling_volatility` retournait une volatilité ANNUALISÉE (facteur ×94) → P(Up) ≈ 0.50 → 100% SKIP
- **Wallet** : vide (0 USDC, 0 POL) — dry-run uniquement

### Refonte v2 (25 mars 2026)

Claude Code Opus 4.6 avec `MASTER_PROMPT_REFONTE_V2.md`. 7 corrections appliquées :
volatilité horaire, bootstrap win_rate, P&L calc, load_dotenv path absolu, guard dry-run ClobClient, asyncio→uvloop setup_cli, Gamma API réelle.

### Correction feeds + vérification MCP (26 mars 2026)

Claude Code Sonnet 4.6. Consultation de la documentation officielle Polymarket via serveur MCP avant toute modification de code. **3 fichiers modifiés, 2 créés.**

**Ce qui a été découvert via MCP** (formats qui différaient des suppositions initiales) :

| Point | Supposé dans le brief | Confirmé par le MCP |
|---|---|---|
| CLOB subscribe `type` | `"subscribe"` | `"market"` |
| CLOB subscribe champ token | `"assets_id"` (singulier) | `"assets_ids"` (pluriel, liste) |
| CLOB event field | `"type"` | `"event_type"` |
| CLOB bids/asks format | tuples `["0.52", "100"]` | objets `{"price": "0.52", "size": "100"}` |
| CLOB token identifier | `"token_id"` | `"asset_id"` |
| RTDS subscribe `action` | `"action": "subscribe"` | `"type": "subscribe"` |
| RTDS subscribe structure | `"subscriptions": [{...}]` array | `"topic": "...", "filter": {...}` plat |
| RTDS event type | `"price_update"` | `"update"` |
| RTDS price field | `data["price"]` | `data["payload"]["value"]` |
| RTDS event `window_start` | existe | **n'existe pas** — capturé par `loop.py` |

**Changements appliqués** :
- `polymarket_clob_ws.py` : subscribe dynamique via `subscribe_assets()`, parser corrigé, cache `best_prices` pour `best_bid_ask`
- `polymarket_rtds.py` : subscribe conforme, parser `payload.value`, méthode `set_price_to_beat()`
- `loop.py` : capture prix Chainlink à T=0, appel `subscribe_assets()` après résolution slugs
- `test_loop_dry.py` : mocks mis à jour
- `test_clob_ws_feed.py` : **nouveau** — 11 tests CLOB WS
- `test_rtds_feed.py` : **nouveau** — 8 tests RTDS
- **Résultat** : 52/52 tests passent

### Fix PING applicatif + re-subscription après reconnexion (26 mars 2026)

Claude Code Sonnet 4.6. Consultation MCP avant modification. **2 fichiers modifiés.**

**Ce qui a été découvert via MCP** :

| Point | Supposé dans le retour reçu | Confirmé par le MCP |
|---|---|---|
| PING format CLOB | `ws.ping()` (protocole RFC 6455) | `send_str("PING")` (text frame applicatif) |
| PING format RTDS | Non précisé | `send_str("PING")` (text frame applicatif) |
| PING fréquence CLOB | 10 secondes | **10 secondes** ✅ |
| PING fréquence RTDS | 5 secondes | **5 secondes** ✅ |
| Réponse serveur | Non précisé | `"PONG"` text frame — doit être ignoré avant `orjson.loads()` |

**Bug collatéral découvert à l'audit** : `"PONG"` arrivant dans `_listen()` déclenchait `orjson.loads("PONG")` → `JSONDecodeError` → reconnexion inutile.

**Changements appliqués** :
- `polymarket_clob_ws.py` : `_ping_loop()` (10s), `_subscribed_token_ids` stocké, re-subscribe auto sur reconnexion, garde `"PONG"` dans `_listen()`
- `polymarket_rtds.py` : `_ping_loop()` (5s), garde `"PONG"` dans `_listen()`
- `test_clob_ws_feed.py` : 5 nouveaux tests (PING, PONG skip, stockage token_ids) → 16 tests total
- `test_rtds_feed.py` : 2 nouveaux tests (PING, PONG skip) → 10 tests total
- **Résultat** : 59/59 tests passent

---

## 3. Contraintes techniques ABSOLUES

Ces règles s'appliquent à **TOUT** le code du projet, sans exception :

1. **`orjson`** pour tout JSON. Jamais `import json` ni `json.loads`/`json.dumps`.
2. **`uvloop`** comme event loop. Tout point d'entrée : `uvloop.run(main())`. Inclut `setup_cli/__main__.py` — **jamais `asyncio.run()`**.
3. **`@dataclass(slots=True)`** pour toute structure fréquemment instanciée (Tick, Order, Signal, TradeResult).
4. **`collections.deque(maxlen=N)`** pour les buffers temporels. Jamais `list` avec `pop(0)`.
5. **Numpy vectorisé** pour tout calcul sur séries de prix. Jamais de boucle `for` Python sur arrays.
6. **`structlog`** JSON pour le logging. Jamais `print()` dans `src/` (autorisé dans `setup_cli/__main__.py` uniquement).
7. **Type hints stricts** sur toute fonction. Compatible `mypy --strict`.
8. **`aiohttp`** pour toute I/O HTTP async. Jamais `requests` (bloquant).
9. **Secrets dans `.env`** uniquement. Jamais hardcodés. `.env` est dans `.gitignore`.
10. **Docstrings Google-style** sur toute fonction publique.
11. **`load_dotenv`** avec path absolu :
    ```python
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")
    ```
    Sans path absolu, le bot ne trouve pas le `.env` si lancé depuis un répertoire différent (fréquent avec tmux).

---

## 4. Architecture du projet

```
polymarket-btc-bot/
├── CLAUDE.md                       ← CE FICHIER
├── AGENTS.md                       ← Contexte permanent Mistral Vibe
├── pyproject.toml                  ← Dépendances PEP 621
├── .env.example                    ← Template variables d'environnement
├── run_bot.sh                      ← Script auto-restart pour RunPod (tmux)
│
├── setup_cli/                      ← Installateur CLI indépendant
│   ├── __init__.py
│   ├── __main__.py                 ← Point d'entrée : python -m setup_cli
│   ├── checker.py                  ← Vérifications système (Python, pip, git)
│   ├── geo_checker.py              ← Test geo-block Polymarket + Binance WS
│   ├── installer.py                ← pip install + vérif imports
│   ├── account_setup.py            ← Guide .env interactif
│   ├── credentials.py              ← Génération API creds L2
│   ├── validator.py                ← Test end-to-end (3 WS + slug + order book)
│   ├── benchmark.py                ← 4 tests de performance (réseau, JSON, décision, CLOB)
│   └── approvals.py                ← Placeholder approbations on-chain
│
├── src/
│   ├── config.py                   ← Config (.env + constantes) ✅
│   ├── feeds/
│   │   ├── binance_ws.py           ← WebSocket Binance aggTrade (aiohttp) ✅
│   │   ├── polymarket_rtds.py      ← WebSocket RTDS Chainlink ✅ (corrigé 26/03)
│   │   ├── polymarket_clob_ws.py   ← WebSocket CLOB order book ✅ (corrigé 26/03)
│   │   └── feed_manager.py         ← Orchestrateur des 3 flux ✅
│   ├── signal/
│   │   ├── delta.py                ← Delta prix actuel vs ouverture ✅
│   │   ├── gbm.py                  ← Modèle GBM analytique P(Up) ✅
│   │   ├── volatility.py           ← Volatilité rolling HORAIRE ✅ (corrigé v2)
│   │   ├── indicators.py           ← RSI, EMA (numpy vectorisé) ✅
│   │   └── scorer.py               ← Score composite → décision ✅
│   ├── strategy/
│   │   ├── taker_selective.py      ← Stratégie taker + logging décisionnel ✅
│   │   ├── kelly.py                ← Kelly conservateur (1/4) ✅ (bootstrap v2)
│   │   └── filters.py              ← Filtres prix, delta, edge ✅
│   ├── execution/
│   │   ├── clob_client.py          ← Wrapper py-clob-client ✅ (guard dry-run)
│   │   ├── order_builder.py        ← Construction ordres GTC ✅
│   │   ├── slug_resolver.py        ← Slug déterministe + MarketData ✅
│   │   └── redeemer.py             ← Auto-redeem + P&L win/loss ✅ (corrigé v2)
│   ├── engine/
│   │   ├── clock.py                ← Sync horloge Unix, T-restant ✅
│   │   ├── loop.py                 ← Boucle 5 min ✅ (corrigé 26/03)
│   │   └── state.py                ← État : bankroll, positions, P&L ✅
│   └── utils/
│       ├── logger.py               ← Logging structlog JSON ✅
│       ├── metrics.py              ← ❌ MANQUANT (mentionné dans AGENTS.md, non bloquant)
│       └── alerter.py              ← Placeholder Telegram (optionnel)
│
└── tests/
    ├── test_delta.py               ✅
    ├── test_gbm.py                 ✅
    ├── test_kelly.py               ✅
    ├── test_slug_resolver.py       ✅
    ├── test_filters.py             ✅
    ├── test_order_builder.py       ✅
    ├── test_loop_dry.py            ✅ (mocks mis à jour 26/03)
    ├── test_volatility.py          ✅ (vérifie vol < 5% = horaire)
    ├── test_taker_logging.py       ✅
    ├── test_clob_ws_feed.py        ✅ NOUVEAU (26/03) — 11 tests CLOB WS
    └── test_rtds_feed.py           ✅ NOUVEAU (26/03) — 8 tests RTDS
```

---

## 5. Statut des bugs — Post-Correction feeds (26 mars 2026)

### ✅ RÉSOLU — CLOB WS subscribe statique

**Root cause de `polymarket_clob: false` au dry-run #1.**
Subscribe envoyait `{"type": "subscribe", "channel": "market", "assets_id": "btc-updown-5m"}`.
- `assets_id` (singulier) → doit être `assets_ids` (pluriel)
- Slug statique → doit être une liste de token IDs hexadécimaux
- Appelé à la connexion → doit être appelé après `resolve_market_data()` dans `loop.py`

**Fix appliqué** : méthode `subscribe_assets(token_ids: list[str])` publique + suppression de `_subscribe()`.

### ✅ RÉSOLU — CLOB WS parser incompatible

`_handle_message()` cherchait `type == "order_book_update"` et `token_id`.
L'API réelle utilise `event_type == "book"` et `asset_id`. Bids/asks = objets `{price, size}` (pas des tuples). Messages arrivent en liste.

**Fix appliqué** : parser entièrement réécrit + cache `best_prices` pour les events `best_bid_ask`.

### ✅ RÉSOLU — RTDS subscribe incorrect

Subscribe envoyait `{"action": "subscribe", "channel": "crypto_prices_chainlink", "symbol": "BTC/USD"}`.
Format réel : `{"type": "subscribe", "topic": "crypto_prices_chainlink", "filter": {"symbol": "btc/usd"}}`.

### ✅ RÉSOLU — RTDS parser incorrect

`_handle_message()` cherchait `type == "price_update"` et `data["price"]`.
Format réel : `type == "update"` et `payload["value"]`. L'event `window_start` n'existe pas.

**Fix appliqué** : `price_to_beat` capturé par `loop.py` à T=0 via `set_price_to_beat()`.

### ✅ RÉSOLU — Volatilité annualisée (root cause dry-run #1, corrigé v2)

`calc_rolling_volatility` appliquait facteur ×94 → P(Up) ≈ 0.50 → 100% SKIP.
Fix : `sqrt(3600 / window_seconds)` au lieu de `sqrt(3600 * 24 * 365 / window_seconds)`.

### ✅ RÉSOLU — Bootstrap win_rate, P&L calc, load_dotenv, guard dry-run, uvloop (corrigés v2)

Voir historique section 2.

### ✅ RÉSOLU — PING applicatif absent + crash PONG (CLOB WS + RTDS) — 26 mars 2026

**Root cause de déconnexions silencieuses + reconnexions inutiles.**

La doc Polymarket (MCP) impose des PINGs applicatifs (text frames, pas RFC 6455) :
- CLOB WS : `"PING"` texte brut toutes les **10 secondes** → serveur répond `"PONG"` texte brut
- RTDS : `"PING"` texte brut toutes les **5 secondes** → serveur répond `"PONG"` texte brut

**Point critique** : `send_str("PING")` (text frame), **pas** `ws.ping()` (ping protocole RFC 6455). aiohttp gère déjà les pings RFC 6455 nativement — `ws.ping()` aurait été ignoré par Polymarket.

**Bug collatéral** : sans garde dans `_listen()`, la réponse `"PONG"` déclenchait `orjson.loads("PONG")` → `JSONDecodeError` → reconnexion inutile toutes les ~10s.

**Fix appliqué** (`polymarket_clob_ws.py` + `polymarket_rtds.py`) :
- `_ping_loop()` : nouvelle méthode, `send_str("PING")` en boucle (10s CLOB, 5s RTDS)
- `connect()` : `asyncio.create_task(_ping_loop())` lancé après connexion, annulé proprement dans `finally` via `ping_task.cancel()` + `await ping_task`
- `_listen()` : garde `if msg.data == "PONG": continue` avant `orjson.loads()`

**Tests ajoutés** : 5 nouveaux tests (PING text frame, PONG skip, stockage token_ids).
**Résultat** : 59/59 tests passent.

### ℹ️ MANQUANT — src/utils/metrics.py

Listé dans `AGENTS.md`, absent du repo. Non bloquant.

---

## 6. Mécanique du marché Polymarket BTC 5m

- Fenêtres de 5 min, démarrent à chaque multiple de 300s Unix.
- Slug déterministe : `btc-updown-5m-{timestamp}` où `timestamp = now - (now % 300)`.
- L'oracle **Chainlink BTC/USD** (pas Binance) détermine le résultat.
- `prix_fin >= prix_début` → "Up" gagne (token paie 1.00$). Sinon "Down" gagne.
- **Frais taker dynamiques** (fév. 2026) : ~1.56% à p=0.50, ~0.13% aux extrêmes. Maximum effectif 1.80% à p=0.50 exact.
- **Ordres maker** : zéro frais + rebates USDC quotidiennes.
- SDK `py-clob-client >= 0.34.5` gère le `feeRateBps` automatiquement.
- Profondeur carnet : ~5 000–15 000$ par côté. Minimum 5 tokens/ordre (~2.50$).
- **Clés API requises** : builder keys depuis https://polymarket.com/settings?tab=builder

---

## 7. Formules mathématiques

### Delta

```
delta = (prix_actuel - prix_ouverture) / prix_ouverture
```

Skip si `|delta| < 0.0003` (0.03%)

### Modèle GBM (probabilité Up)

```
P(Up) = Φ(delta / (σ_hourly × √(t_remaining / 3600)))
```

- Φ = `scipy.stats.norm.cdf`
- σ_hourly = volatilité **HORAIRE** BTC — facteur `sqrt(3600 / window_seconds)` — **JAMAIS annualisé**
- t_remaining = secondes restantes dans la fenêtre

### Kelly conservateur

```
f* = (win_rate × (1/price - 1) - (1 - win_rate)) / (1/price - 1)
bet = min(f* × 0.25 × bankroll, bankroll × 0.05)
bet = max(bet, 2.50)   # minimum Polymarket
```

Si f* ≤ 0 : ne pas miser. **Bootstrap** : `BOOTSTRAP_WIN_RATE = 0.65` pour les 20 premiers trades.

### Espérance de valeur

```
EV = win_rate × (1/price - 1) - (1 - win_rate)
```

EV > 0 ssi `win_rate > price + fee_rate`.

---

## 8. Séquence de la boucle principale (état actuel — post 26/03)

```
T=0s      → window_start = get_window_start()
           → opening_price = rtds_feed.get_chainlink_price()
           →   Si None → logger.error + return (RTDS pas encore connecté)
           → rtds_feed.set_price_to_beat(opening_price)
           → slug = get_current_slug(timestamp=window_start)
           → market_data = await resolve_market_data(slug)   # Gamma API
           →   Si None → logger.error + return
           → await clob_feed.subscribe_assets([up_token_id, down_token_id])  ← DYNAMIQUE

T=0-270s  → Accumuler ticks Binance dans deque(maxlen=600)
           → Calculer rolling stats (volatility, RSI, EMA)

T=270s    → evaluate_window() :
           →   delta = (current_price - price_to_beat) / price_to_beat
           →   Si |delta| < 0.0003 → SKIP
           →   volatility_hourly = calc_rolling_volatility(buffer, 300)
           →   Si len(buffer) < 20 → SKIP
           →   gbm_prob = calc_up_probability(delta, volatility_hourly, t_remaining)
           →   signal = scorer.score(...)
           →   best_ask = clob_ws.get_best_ask(token_id)
           →   Si best_ask is None → SKIP
           →   should_execute, reason = should_trade(signal, best_ask, state)
           →   bet_size = calc_kelly_bet(win_rate, best_ask, bankroll)
           →   Retourner TradeDecision ou None

T=285s    → Si TradeDecision et mode != "dry-run" :
           →   build_and_post_order(client, token_id, side, price, size)

T=295s    → cancel_all() (safety net)

T=300s+   → sleep RESOLUTION_WAIT_SECONDS (15s)

T=315s    → Si mode != "dry-run" :
           →   redeem_if_resolved() + P&L + state.update_after_trade()
```

---

## 9. APIs externes — Formats MCP-vérifiés (26 mars 2026)

| Endpoint | URL | Usage |
|---|---|---|
| Binance WS | `wss://stream.binance.com:9443/ws/btcusdt@aggTrade` | Prix BTC live |
| Binance WS (fallback) | `wss://stream.binance.vision/ws/btcusdt@aggTrade` | Si IP bloquée |
| Polymarket RTDS | `wss://ws-live-data.polymarket.com` | Prix Chainlink |
| Polymarket CLOB WS | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | Order book |
| Polymarket CLOB REST | `https://clob.polymarket.com` | Ordres, positions |
| Polymarket Gamma | `https://gamma-api.polymarket.com` | Métadonnées marché |

### CLOB WebSocket — Formats exacts

**Subscribe** (envoyé depuis `loop.py` après `resolve_market_data()`) :
```json
{
  "type": "market",
  "assets_ids": ["<up_token_id>", "<down_token_id>"],
  "custom_feature_enabled": true
}
```
> `custom_feature_enabled: true` est nécessaire pour recevoir les events `best_bid_ask`, `new_market`, `market_resolved`.

**PING** : toutes les 10 secondes.

**Event `book`** — snapshot complet :
```json
{
  "event_type": "book",
  "asset_id": "0x...",
  "market": "0x...",
  "bids": [{"price": "0.48", "size": "100"}],
  "asks": [{"price": "0.52", "size": "80"}],
  "timestamp": "1710000000000",
  "hash": "0x..."
}
```

**Event `best_bid_ask`** — top of book (nécessite `custom_feature_enabled: true`) :
```json
{
  "event_type": "best_bid_ask",
  "asset_id": "0x...",
  "market": "0x...",
  "best_bid": "0.48",
  "best_ask": "0.52",
  "spread": "0.04",
  "timestamp": "1710000000000"
}
```

**Autres events reçus** (non utilisés par le bot) : `price_change`, `last_trade_price`, `tick_size_change`, `new_market`, `market_resolved`.

**Points critiques** :
- Le champ type des events est `event_type` (pas `type`)
- L'identifiant du token est `asset_id` (pas `token_id`)
- Les bids/asks sont des **objets** `{price: string, size: string}` (pas des tuples)
- Les messages peuvent arriver en **liste** `[{...}, {...}]`

### RTDS — Formats exacts

**Subscribe** :
```json
{
  "type": "subscribe",
  "topic": "crypto_prices_chainlink",
  "filter": {"symbol": "btc/usd"}
}
```
> `type` (pas `action`) — `topic` + `filter` plats (pas array `subscriptions`) — symbol en minuscules avec slash.

**PING** : toutes les 5 secondes.

**Event de prix** :
```json
{
  "topic": "crypto_prices_chainlink",
  "type": "update",
  "timestamp": 1710000000000,
  "payload": {
    "symbol": "btc/usd",
    "value": 67234.50,
    "timestamp": 1710000000000
  }
}
```
> `type == "update"` (pas `"price_update"`) — le prix est dans `payload["value"]` (pas `data["price"]`).

---

## 10. API py-clob-client — Référence

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

client = ClobClient(
    host="https://clob.polymarket.com",
    key="0x_PRIVATE_KEY",
    chain_id=137,
    signature_type=0,
    funder="0x_FUNDER_ADDRESS"
)
creds = client.create_or_derive_api_creds()
client.set_api_creds(creds)

# Toutes les méthodes sont SYNCHRONES → asyncio.to_thread en contexte async
book  = await asyncio.to_thread(client.get_order_book, token_id)
price = await asyncio.to_thread(client.get_price, token_id, "BUY")

order_args = OrderArgs(token_id=token_id, price=0.55, size=10.0, side=BUY)
signed = await asyncio.to_thread(client.create_order, order_args)
resp   = await asyncio.to_thread(client.post_order, signed, OrderType.GTC)

await asyncio.to_thread(client.cancel, order_id)
await asyncio.to_thread(client.cancel_all)
await asyncio.to_thread(client.redeem, condition_id)
```

---

## 11. Dépendances

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "uvloop>=0.22.0",
    "orjson>=3.10.0",
    "aiohttp>=3.9.0",
    "py-clob-client>=0.34.5",
    "numpy>=1.26.0",
    "scipy>=1.12.0",
    "structlog>=24.0.0",
    "python-dotenv>=1.0.0",
    "web3>=7.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0", "mypy>=1.0.0", "ruff>=0.4.0"]
```

---

## 12. Variables d'environnement (.env)

```env
POLYMARKET_PRIVATE_KEY=0x...        # Clé privée Polygon (Phantom)
POLYMARKET_FUNDER=0x...             # Adresse proxy wallet
POLYMARKET_API_KEY=...              # Builder keys (polymarket.com/settings?tab=builder)
POLYMARKET_API_SECRET=...
POLYMARKET_PASSPHRASE=...
POLYGON_RPC_URL=https://polygon-rpc.com
BOT_MODE=dry-run                    # dry-run | safe
LOG_LEVEL=DEBUG                     # DEBUG pour valider feeds, INFO prod
```

---

## 13. Configuration RunPod (déploiement)

```bash
# Setup initial
cd /workspace
git clone https://github.com/<username>/polymarket-btc-bot.git
cd polymarket-btc-bot
pip install -e ".[dev]" --break-system-packages
cp .env.example .env && nano .env

# Lancement avec auto-restart
tmux new-session -d -s bot -x 220 -y 50
tmux send-keys -t bot "cd /workspace/polymarket-btc-bot && ./run_bot.sh" Enter

# Monitoring
tmux attach -t bot
tail -f /workspace/bot.log
```

**Checklist post-lancement (0–15 min)** :
```bash
grep "Connected to" /workspace/bot.log           # 3 lignes attendues
grep "Market data resolved" /workspace/bot.log    # slugs OK
grep "Price to beat set" /workspace/bot.log       # RTDS + loop OK
grep "Subscribed to CLOB assets" /workspace/bot.log  # CLOB subscribe OK
grep "Health check completed" /workspace/bot.log | tail -3
grep "Signal evaluated" /workspace/bot.log | head -5
```

**Diagnostic CLOB WS** (si `polymarket_clob: false` persiste) :
```bash
# Vérifier que les raw messages ont bien event_type "book" ou "best_bid_ask"
grep "Raw WS message" /workspace/bot.log | grep -v "binance" | head -10
# Si vide → le subscribe n'a pas été envoyé (subscribe_assets non appelé)
# Si présent → vérifier event_type dans les messages
```

---

## 14. Commandes de développement

```bash
# Tests unitaires
pytest tests/ -v

# Vérifier la volatilité (doit être sqrt(3600/window), PAS sqrt(3600*24*365/window))
grep "annualization_factor\|hourly_factor\|3600" src/signal/volatility.py

# Vérifier absence de json standard
grep -rn "import json$\|from json " src/

# Vérifier absence de print() dans src/
grep -rn "print(" src/ | grep -v "__main__"

# Vérifier que le subscribe CLOB est dynamique (aucun slug statique)
grep -n "btc-updown-5m\|assets_id[^s]" src/feeds/polymarket_clob_ws.py

# Vérifier que le subscribe RTDS est conforme
grep -n "crypto_prices_chainlink\|btc/usd" src/feeds/polymarket_rtds.py

# Vérifier que subscribe_assets et set_price_to_beat sont appelés dans loop.py
grep -n "subscribe_assets\|set_price_to_beat" src/engine/loop.py

# Lint + type check
ruff check src/
mypy --strict src/

# Setup CLI
python3 -m setup_cli

# Lancer le bot
python3 -m src --mode dry-run --log-level DEBUG
```

---

## 15. Workflow de développement

1. **Développement** : Mistral Vibe (Devstral 2) crée les modules par étapes.
2. **Review** : Claude Code juge la qualité, vérifie les contraintes, corrige avec les MASTER_PROMPT correspondants.
3. **Tests** : `pytest tests/ -v` après chaque modification.
4. **Lint** : `ruff check src/` + `mypy --strict src/`
5. **Analyse logs** : `parse_bot_log.py` pour compresser les logs volumineux (750k+ lignes → ~5k lignes) avant soumission à Claude Code.
6. **Déploiement** : `git push` → `git pull` sur pod RunPod → dry-run → live.

**Règle MCP** : Avant toute modification touchant une API externe (CLOB WS, RTDS, Gamma), consulter le serveur MCP Polymarket pour confirmer le format exact. Ne jamais supposer. Le MCP a autorité sur les suggestions du brief si elles diffèrent.

---

## 16. Points de vigilance pour Claude Code

1. **La volatilité est HORAIRE** — facteur `sqrt(3600 / window_seconds)`. Si `sqrt(3600 * 24 * 365 / ...)` apparaît, c'est le bug racine du dry-run #1.

2. **Le subscribe CLOB est dynamique** — `subscribe_assets()` appelé dans `loop.py` après `resolve_market_data()`, pas à la connexion. La méthode `_subscribe()` a été supprimée.

3. **CLOB WS : `event_type` pas `type`** — et `asset_id` pas `token_id`. Bids/asks = objets `{price, size}` en strings. Messages peuvent arriver en liste.

4. **RTDS : `payload["value"]` pas `data["price"]`** — et `type == "update"` pas `"price_update"`. L'event `window_start` n'existe pas dans l'API réelle.

5. **`price_to_beat` est capturé par `loop.py`** à T=0 via `get_chainlink_price()` + `set_price_to_beat()`. Le RTDS ne l'envoie pas automatiquement.

6. **`PolymarketClient`** uniquement en mode `safe`/`live`. Guard dans `loop.py`.

7. **`asyncio.to_thread()`** pour tout appel py-clob-client (API synchrone).

8. **`load_dotenv`** toujours avec path absolu `Path(__file__).parent.parent / ".env"`.

9. **Tests `test_loop_dry.py`** : mocks RTDS exposent `get_chainlink_price` + `set_price_to_beat` + `get_price_to_beat`. Mock CLOB expose `subscribe_assets` comme `AsyncMock`.

10. **Bootstrap win_rate** : `BOOTSTRAP_WIN_RATE = 0.65` pour les 20 premiers trades — sinon Kelly retourne 0.

11. **PING applicatifs WS** : Les deux feeds envoient `send_str("PING")` (text frame). **Ne jamais utiliser `ws.ping()`** (ping protocole RFC 6455) — Polymarket l'ignore. CLOB : 10s. RTDS : 5s.

12. **Garde "PONG" dans `_listen()`** : Le serveur répond `"PONG"` (text frame brut, pas JSON). Le `if msg.data == "PONG": continue` dans les deux `_listen()` est **indispensable** — sans lui, `orjson.loads("PONG")` lève une exception et provoque une reconnexion inutile toutes les 10s.

13. **Re-subscription CLOB après reconnexion** : `subscribe_assets()` stocke les token_ids dans `self._subscribed_token_ids`. `connect()` les réutilise automatiquement à chaque reconnexion. Ne pas supprimer cette logique.

14. **`_ping_loop` annulé dans `finally`** : Pattern obligatoire dans `connect()` après tout `await self._listen()` :
    ```python
    ping_task = asyncio.create_task(self._ping_loop())
    try:
        await self._listen()
    finally:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
    ```
