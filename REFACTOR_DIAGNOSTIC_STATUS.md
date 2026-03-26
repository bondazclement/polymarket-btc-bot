# Refonte Polymarket BTC Bot — État d'avancement, diagnostic complet et détails des modifications

Date: 2026-03-26  
Auteur: Assistant Codex  
Contexte: dry-run sur pod RunPod (`/workspace/polymarket-btc-bot`)

---

## 1) Résumé exécutif

Le bot a été bloqué principalement par un enchaînement de problèmes de robustesse runtime plutôt que par la stratégie pure:

1. **Mismatch d'API RTDS dans la boucle** (`get_chainlink_price` absent selon la forme d'objet chargée), causant des erreurs répétées et empêchant toute progression de fenêtre.
2. **Boucle de retry intra-fenêtre** (log spam toutes ~5s) qui masquait les signaux utiles et empêchait une exécution déterministe.
3. **Faible observabilité pratique** pour diagnostiquer RTDS/CLOB en conditions réelles.
4. **Fragilité de keepalive CLOB/RTDS** selon les sémantiques text `PING/PONG`.
5. **Incohérence de contrat de retour dans le redeemer** (appelant attendait `(pnl, is_win)` alors que la fonction pouvait renvoyer un scalaire).

La refonte a visé à rendre le système **résilient**, **diagnosticable** et **cohérent de bout en bout**.

---

## 2) Diagnostic détaillé observé en dry-run

### 2.1 Symptômes dans les logs

- Multiples événements `"New window started"` dans la même fenêtre temporelle.
- Erreur répétée:
  - `'PolymarketRTDS' object has no attribute 'get_chainlink_price'`
- Health checks montrant:
  - `binance: true`
  - `polymarket_clob: true`
  - `polymarket_rtds: false`
- Absence de traces de progression complète:
  - pas de `"Signal evaluated"`
  - pas de `"Trade decision made"`

### 2.2 Interprétation

- Le code rentrait bien dans la boucle principale, mais cassait tôt, avant les étapes de décision.
- Le redémarrage rapide dans la même fenêtre produisait du bruit, pas du progrès.
- Le feed RTDS fonctionnait côté protocole, mais la boucle ne parvenait pas à consommer correctement le prix d'ouverture de façon stable.

---

## 3) Modifications de refonte réalisées (détaillées)

> Cette section détaille les changements introduits pour stabiliser le dry-run.

### 3.1 Lancement et environnement

#### `run_bot.sh` (nouveau)
- Ajout d'un lanceur shell pour:
  - fixer le `cwd` à la racine du repo,
  - injecter `PYTHONPATH` pour les imports locaux,
  - démarrer `python3 -m src`,
  - permettre soit des arguments pass-through, soit des defaults via `BOT_MODE` / `LOG_LEVEL`.

**Objectif**: éliminer les erreurs de contexte d'exécution (imports/module path).

#### `src/config.py`
- `load_dotenv` rendu déterministe via chemin absolu basé sur `Path(...)`.

**Objectif**: éviter les env vides selon le répertoire de lancement.

---

### 3.2 Trading loop

#### `src/engine/loop.py`
- Passage explicite de `signal_scorer` à `evaluate_window`.
- Ajout d'un getter compatible `_get_opening_chainlink_price()` avec fallback:
  1) `get_chainlink_price()`
  2) `get_current_price()`
  3) attribut `current_price`
- Changement de stratégie en cas d'exception dans `run()`:
  - attendre la prochaine frontière de fenêtre plutôt que retry toutes les 5s.

**Objectif**: éviter les crash loops intra-fenêtre et sécuriser l'accès prix d'ouverture.

---

### 3.3 Feed RTDS

#### `src/feeds/polymarket_rtds.py`
- Subscribe RTDS avec `orjson` et format `subscriptions[]` attendu.
- Keepalive `PING` text périodique.
- Parse robuste des formats observés:
  - batch `payload.data[]`
  - update unitaire `payload.value`
- Tracking de `last_price_ts` pour distinguer liveness socket vs fraîcheur prix.
- Ajout alias `get_current_price()` (compatibilité).

**Objectif**: robustesse protocolaire + compatibilité + health check plus fiable.

---

### 3.4 Feed CLOB

#### `src/feeds/polymarket_clob_ws.py`
- Keepalive text `PING` + gestion `PONG`.
- Re-subscribe automatique après reconnexion.
- Parsing enrichi:
  - `book`
  - `best_bid_ask`
  - `price_change`
  - `tick_size_change` (cache `tick_sizes`)
- `subscribe_assets()` mémorise les token IDs.

**Objectif**: stabiliser la réception de prix/exécution et éviter feed silencieux après reconnect.

---

### 3.5 Feed manager / santé

#### `src/feeds/feed_manager.py`
- Health RTDS basé sur `max(last_message_ts, last_price_ts)`.

**Objectif**: réduire les faux négatifs de santé RTDS.

---

### 3.6 Exécution / post-trade

#### `src/execution/redeemer.py`
- Contrat corrigé: `redeem_if_resolved(...) -> tuple[pnl, is_win] | None`
- Gestion cohérente du cas où les données d'entrée sont absentes.

**Objectif**: cohérence type/runtime avec la boucle d'appel.

---

### 3.7 Stratégie

#### `src/strategy/taker_selective.py`
- Skip explicite si `abs(delta) < DELTA_MIN` (log raison).

#### `src/strategy/filters.py`
- Suppression du seuil hard-coded de confiance qui bloquait trop agressivement.

**Objectif**: aligner le comportement dry-run avec la logique phase 1 (sélectif mais pas muet).

---

### 3.8 Outillage de diagnostic

#### `scripts/diagnose_rtds.py` (nouveau)
- Script autonome de test RTDS:
  - subscribe correct,
  - logs des frames,
  - PING sur timeout.

#### `scripts/diagnose_clob_ws.py` (nouveau)
- Script autonome CLOB:
  - subscribe via token IDs réels,
  - summary par `event_type`,
  - PING/PONG robuste.

**Objectif**: industrialiser le diagnostic live sans bricolage ad-hoc.

---

## 4) Validation exécutée

Checks réalisés pendant la refonte:

- Compilation:
  - `python -m compileall src tests`
  - `python -m compileall scripts src tests`
- Tests ciblés:
  - `pytest -q tests/test_rtds_feed.py::test_get_current_price_alias`
  - `pytest -q tests/test_loop_dry.py::test_get_opening_chainlink_price_falls_back_to_current_price_attr`
  - `pytest -q tests/test_redeemer.py`

Résultat: les tests ciblés exécutables localement sont passés.

---

## 5) Limites connues et risques résiduels

1. **Plugin pytest async** manquant dans certains environnements => partielle non-exécution de certains tests `@pytest.mark.asyncio`.
2. **Niveau de log**: certaines investigations nécessitent DEBUG strict et rotation de logs maîtrisée.
3. **Qualité des inputs de diagnostic CLOB**:
   - si token IDs placeholders/invalides, on peut voir `PONG` sans events market.
4. **Variabilité API live**:
   - certains payloads peuvent varier (batch vs unitaire), d'où nécessité de parse défensif maintenu.

---

## 6) Plan “refonte totale” recommandé (prochaine étape)

### Étape A — Orchestrateur strict par fenêtre (state machine)
- États explicites: `INIT -> OPEN_CAPTURED -> MARKET_RESOLVED -> CLOB_SUBSCRIBED -> SIGNAL_READY -> DECISION -> DONE`.
- Une seule tentative structurée par fenêtre.

### Étape B — Contrats de données typed + validation
- Enveloppes dataclass pour messages RTDS/CLOB normalisés.
- Validation minimale de schéma avant update state.

### Étape C — Observabilité par fenêtre
- Correlation ID = `window_start`.
- Logs de checkpoints obligatoires avec raisons de skip.

### Étape D — Garde-fous de progression
- Timeout explicite pour chaque étape.
- Si échec d'étape, passer à la fenêtre suivante proprement (pas de spin).

### Étape E — Tests d'intégration “offline-like”
- Fixtures de frames RTDS/CLOB réelles capturées.
- Test de progression complète d'une fenêtre dry-run.

---

## 7) Commandes opérationnelles utiles

### Démarrage
```bash
cd /workspace/polymarket-btc-bot
./run_bot.sh
```

### RTDS diagnostic
```bash
python3 scripts/diagnose_rtds.py --symbol btc/usd --samples 20 --timeout 8
```

### CLOB diagnostic (IDs réels requis)
```bash
python3 scripts/diagnose_clob_ws.py --token-id <UP_ID> --token-id <DOWN_ID> --samples 40 --timeout 10
```

### Logs de progression fenêtre
```bash
grep -E "Error in trading window|New window started|Market data resolved|Subscribed to CLOB assets|Signal evaluated|No trade decision|Trade decision made" /workspace/bot.log | tail -n 200
```

---

## 8) Conclusion

L'état actuel de la refonte a corrigé les points les plus bloquants de dry-run:
- crash loops,
- mismatch API RTDS,
- manque d'outillage diagnostic,
- incohérence de contrat redeemer.

La prochaine itération recommandée est une refonte de l'orchestration par **state machine** afin de garantir une progression déterministe et une observabilité irréprochable à chaque fenêtre de 5 minutes.

