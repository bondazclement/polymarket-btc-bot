# AGENTS.md — Polymarket BTC UpDown 5m Trading Bot

> Ce fichier est lu automatiquement par Mistral Vibe à chaque session.
> Il constitue la mémoire permanente du projet pour l'agent de code.

---

## 1. Identité du projet

**Nom** : polymarket-btc-bot
**Objectif** : Bot de trading automatisé pour les marchés binaires "BTC Up or Down - 5 Minutes" sur Polymarket. Chaque fenêtre de 5 minutes, le bot décide d'acheter un token "Up" ou "Down" (ou de ne rien faire) en comparant le prix BTC en temps réel (Binance) avec le prix oracle Chainlink utilisé pour la résolution.

**Stratégie Phase 1** : Taker sélectif — n'entre que lorsque le signal est fort (delta ≥ 0.03%, token ≤ 0.60$), en utilisant un modèle GBM analytique pour estimer la probabilité de gain.

**Capital** : 100$ USDC. Sizing via Kelly conservateur (1/4).

---

## 2. Contraintes techniques ABSOLUES

Ces règles s'appliquent à **TOUT** le code du projet, sans exception.

### Performance & I/O
- **Event loop** : `uvloop` obligatoire. Tout point d'entrée doit utiliser `uvloop.run(main())`.
- **JSON** : `orjson.loads()` et `orjson.dumps()` PARTOUT. Ne JAMAIS utiliser `import json` ni `json.loads`/`json.dumps`. `orjson` est 5-10x plus rapide (écrit en Rust).
- **WebSocket Binance** : `picows` (la bibliothèque WebSocket la plus rapide en Python). Acceptable : `aiohttp` pour les autres WebSockets (RTDS, CLOB).
- **HTTP async** : `aiohttp` uniquement. Ne JAMAIS utiliser `requests` (bloquant).
- **Pas de polling** : tout est event-driven via WebSocket ou callback async.

### Structures de données
- **Dataclasses** : `@dataclass(slots=True)` pour TOUTE structure fréquemment instanciée (Tick, Order, Signal, TradeResult). Les slots éliminent `__dict__` et accélèrent l'accès de ~30%.
- **Buffers temporels** : `collections.deque(maxlen=N)` pour les séries de prix. Jamais de `list` avec `pop(0)` (O(n) vs O(1)).
- **Pas de dict quand un dataclass suffit** : les dictionnaires sont pour les données dynamiques (JSON brut), les dataclasses pour les données typées.

### Calcul numérique
- **Numpy vectorisé** : pour volatilité, RSI, EMA, et toute opération sur des séries de prix. JAMAIS de boucle `for` Python sur des arrays de prix.
- **Scipy** : `scipy.stats.norm.cdf` pour le modèle GBM. Pré-calculer ce qui est statique.

### Qualité du code
- **Type hints** : obligatoires sur TOUTE fonction, TOUT paramètre, TOUT retour. Compatible `mypy --strict`.
- **Docstrings** : obligatoires sur toute fonction publique. Format Google style.
- **Logging** : `structlog` avec sortie JSON. JAMAIS `print()`. Chaque log inclut timestamp, module, niveau.
- **Pas de global mutable** : l'état est centralisé dans `src/engine/state.py`, passé explicitement.
- **Gestion d'erreurs** : `try/except` ciblé. Jamais de `except Exception: pass`. Logger chaque erreur.

### Sécurité
- Les clés privées sont dans `.env` (jamais hardcodées).
- `.env` est dans `.gitignore`.
- Aucun secret ne doit apparaître dans les logs (masquer les clés).

---

## 3. Architecture du projet

```
polymarket-btc-bot/
├── AGENTS.md                  ← CE FICHIER (contexte permanent Vibe)
├── pyproject.toml             ← Dépendances PEP 621
├── .env.example               ← Template variables d'environnement
│
├── setup_cli/                 ← Installateur CLI indépendant
│   ├── __main__.py            ← Point d'entrée : python -m setup_cli
│   ├── checker.py             ← Vérification dépendances système
│   ├── installer.py           ← Installation auto des packages
│   ├── account_setup.py       ← Guide interactif comptes + clés
│   ├── approvals.py           ← Approbations on-chain (USDC, CTF)
│   ├── credentials.py         ← Génération API credentials Polymarket
│   └── benchmark.py           ← 4 tests de performance
│
├── src/                       ← Code principal du bot
│   ├── config.py              ← Configuration (.env + constantes)
│   ├── feeds/                 ← Flux temps réel
│   │   ├── binance_ws.py      ← WebSocket Binance aggTrade (picows)
│   │   ├── polymarket_rtds.py ← WebSocket RTDS Chainlink
│   │   ├── polymarket_clob_ws.py ← WebSocket CLOB order book
│   │   └── feed_manager.py    ← Orchestrateur des 3 flux
│   ├── signal/                ← Calcul du signal
│   │   ├── delta.py           ← Delta prix actuel vs ouverture
│   │   ├── gbm.py             ← Modèle GBM analytique P(Up)
│   │   ├── volatility.py      ← Volatilité rolling (numpy)
│   │   ├── indicators.py      ← RSI, EMA spread (numpy)
│   │   └── scorer.py          ← Score composite → décision
│   ├── strategy/              ← Logique de décision
│   │   ├── taker_selective.py ← Stratégie taker haute conviction
│   │   ├── kelly.py           ← Kelly conservateur (1/4)
│   │   └── filters.py         ← Filtres : prix, delta, edge
│   ├── execution/             ← Exécution des ordres
│   │   ├── clob_client.py     ← Wrapper py-clob-client + retry
│   │   ├── order_builder.py   ← Construction ordres + feeRateBps
│   │   ├── slug_resolver.py   ← Slug déterministe + token IDs
│   │   └── redeemer.py        ← Auto-redeem post-résolution
│   ├── engine/                ← Boucle principale
│   │   ├── clock.py           ← Sync horloge Unix, T-restant
│   │   ├── loop.py            ← Boucle 5 min complète
│   │   └── state.py           ← État : bankroll, positions, P&L
│   └── utils/                 ← Utilitaires
│       ├── logger.py          ← Logging structuré JSON
│       ├── metrics.py         ← P&L, win rate, drawdown
│       └── alerter.py         ← Alertes Telegram (optionnel)
│
├── tests/                     ← Tests pytest
├── benchmarks/                ← Benchmarks performance
└── scripts/                   ← Scripts utilitaires
```

---

## 4. Mécanique du marché (ce que le bot doit comprendre)

### Résolution
- Chaque fenêtre démarre à un multiple de 300 secondes Unix.
- Slug déterministe : `btc-updown-5m-{timestamp}` où timestamp = `now - (now % 300)`.
- L'oracle **Chainlink BTC/USD** (pas Binance) détermine le résultat.
- Si `prix_chainlink_fin >= prix_chainlink_début` → "Up" gagne. Sinon "Down" gagne.
- Le token gagnant paie 1.00$. Le perdant paie 0.00$.

### Frais (CRITIQUE — février 2026)
- Les marchés 5m ont des **frais taker dynamiques** : ~1.56% à p=0.50, ~0.13% aux extrêmes.
- Les **ordres maker** (limit passifs) ne paient PAS de frais et reçoivent des **rebates USDC quotidiennes**.
- Le SDK `py-clob-client` gère automatiquement le `feeRateBps` depuis v0.34.5.
- TOUJOURS fetch le fee rate dynamiquement avant de signer un ordre. Ne JAMAIS hardcoder.

### Profondeur du carnet
- ~5 000 à 15 000$ par côté en session active.
- Minimum 5 tokens par ordre (~2.50$ à p=0.50).

### APIs utilisées
- **Binance WebSocket** : `wss://stream.binance.com:9443/ws/btcusdt@aggTrade` (prix BTC live)
- **Polymarket RTDS** : `wss://ws-live-data.polymarket.com` (prix Chainlink, price_to_beat)
- **Polymarket CLOB WS** : `wss://ws-subscriptions-clob.polymarket.com/ws/market` (order book)
- **Polymarket CLOB REST** : `https://clob.polymarket.com` (ordres, positions)
- **Polymarket Gamma** : `https://gamma-api.polymarket.com` (métadonnées marchés)

---

## 5. Formules mathématiques clés

### Delta
```
delta = (prix_actuel - prix_ouverture) / prix_ouverture
```
- Si |delta| < 0.0003 (0.03%) → ne pas trader (signal trop faible).

### Modèle GBM (probabilité Up)
```
P(Up) = Φ(delta / (σ_hourly × √(t_remaining / 3600)))
```
- Φ = CDF normale standard (`scipy.stats.norm.cdf`)
- σ_hourly = volatilité horaire BTC (calculée en rolling sur les 300 dernières secondes)
- t_remaining = secondes restantes dans la fenêtre

### Kelly conservateur
```
f* = (win_rate × (1/price - 1) - (1 - win_rate)) / (1/price - 1)
bet = min(f* × 0.25 × bankroll, bankroll × 0.05)
```
- Si f* ≤ 0 : ne pas miser.
- Minimum = 2.50$ (5 tokens × ~0.50$)

### Espérance de valeur
```
EV = win_rate × (1/price - 1) - (1 - win_rate)
```
- EV > 0 si et seulement si win_rate > price.
- Avec les frais taker, le seuil effectif est : win_rate > price + fee_rate.

---

## 6. Séquence de la boucle principale (par fenêtre de 5 min)

```
T=0s     → Enregistrer prix Chainlink ouverture, calculer slug, résoudre token_ids
T=0-270s → Accumuler ticks Binance, calculer stats rolling (volatilité, RSI)
T=270s   → Évaluer delta. Si |delta| < 0.03% → SKIP cette fenêtre
T=275s   → Fetch order book. Vérifier : best_ask ≤ 0.60$
T=280s   → Calculer P(Up) via GBM. Comparer à best_ask + edge_buffer (0.05)
T=285s   → Si edge suffisant : placer l'ordre (taker limit, GTC)
T=295s   → Cancel si non exécuté
T=300s+  → Attendre résolution Chainlink
T=310s   → Auto-redeem, logger résultat, MAJ bankroll, recalculer Kelly
```

---

## 7. Dépendances exactes

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "uvloop>=0.22.0",
    "orjson>=3.10.0",
    "picows>=1.0.0",
    "aiohttp>=3.9.0",
    "py-clob-client>=0.34.5",
    "numpy>=1.26.0",
    "scipy>=1.12.0",
    "structlog>=24.0.0",
    "python-dotenv>=1.0.0",
    "web3>=7.0.0",
]
```

---

## 8. Variables d'environnement requises

```env
POLYMARKET_PRIVATE_KEY=0x...   # Clé privée EOA Polygon (signe les ordres)
POLYMARKET_FUNDER=0x...        # Adresse proxy wallet Polymarket
POLYMARKET_API_KEY=...         # Credential L2 (générée par script)
POLYMARKET_API_SECRET=...      # Credential L2
POLYMARKET_PASSPHRASE=...      # Credential L2
POLYGON_RPC_URL=https://...    # RPC Polygon (public ou premium)
BOT_MODE=dry-run               # dry-run | safe | aggressive
LOG_LEVEL=INFO                 # DEBUG | INFO | WARNING | ERROR
```

---

## 9. Conventions de code

- **Imports** : stdlib → third-party → local, séparés par une ligne vide.
- **Nommage** : snake_case pour fonctions/variables, PascalCase pour classes, UPPER_SNAKE pour constantes.
- **Longueur de ligne** : 100 caractères max (configurer ruff).
- **Tests** : chaque module `src/x/y.py` a un test `tests/test_y.py`. Tests rapides (<1s), isolés, sans réseau.
- **Async** : toute fonction faisant du I/O est `async def`. Pas de mélange sync/async.
- **Erreurs** : exceptions custom dans `src/utils/exceptions.py` si nécessaire. Toujours log avant de raise.

---

## 10. Workflow de développement

1. **Développement** : Mistral Vibe (Devstral 2) crée les modules par étapes.
2. **Review** : Claude Code juge la qualité, vérifie les contraintes, refactorise si nécessaire.
3. **Tests** : `pytest tests/ -v` après chaque étape.
4. **Lint** : `ruff check src/` + `mypy --strict src/`
5. **Benchmark** : `python -m setup_cli` pour les 4 tests de performance sur le VPS.
6. **Déploiement** : git push → git pull sur VPS → benchmark → dry-run 48h → live.
