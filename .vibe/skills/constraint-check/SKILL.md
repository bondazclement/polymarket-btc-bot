---
name: constraint-check
description: Vérifie que le projet respecte toutes les contraintes architecturales définies dans AGENTS.md (imports, structure, sécurité, conventions).
license: MIT
compatibility: Python 3.11+
user-invocable: true
allowed-tools:
  - read_file
  - grep
  - bash
---

# /constraint-check — Vérification des Contraintes Architecturales

Tu es un architecte logiciel qui audite la conformité du projet aux spécifications.

## Ta mission

Vérifie systématiquement que le projet respecte TOUTES les contraintes définies dans `AGENTS.md`. Produis un rapport de conformité.

## Checklist de vérification

### 1. Structure du projet
- [ ] Vérifier que tous les dossiers de l'arborescence existent : `src/feeds/`, `src/signal/`, `src/strategy/`, `src/execution/`, `src/engine/`, `src/utils/`, `setup_cli/`, `tests/`, `benchmarks/`
- [ ] Vérifier que chaque dossier `src/*/` contient un `__init__.py`
- [ ] Vérifier que `pyproject.toml` existe et contient les dépendances requises (uvloop, orjson, picows, aiohttp, py-clob-client, numpy, scipy, structlog, python-dotenv)

### 2. Sécurité
- [ ] `.env` est dans `.gitignore` : `grep -q "\.env" .gitignore`
- [ ] Aucune clé privée hardcodée : `grep -rn "0x[a-fA-F0-9]\{64\}" src/` (ne devrait rien retourner)
- [ ] Aucun secret dans les logs : chercher des `log.*private\|log.*secret\|log.*key` dans src/
- [ ] Les variables sensibles viennent de `.env` : vérifier que `config.py` utilise `os.getenv()` ou `dotenv`

### 3. Dépendances correctes
```bash
# Vérifier les imports interdits
grep -rn "import json$\|from json " src/        # INTERDIT (utiliser orjson)
grep -rn "import requests\|from requests" src/   # INTERDIT (utiliser aiohttp)
grep -rn "^import time$" src/                     # SUSPECT (time.sleep bloquant)
```

### 4. Conventions de code
- [ ] Tous les fichiers `src/**/*.py` ont un module docstring (première ligne après les imports est une docstring)
- [ ] Ordre des imports respecté : `bash: isort --check-only --diff src/` (si isort installé)
- [ ] Pas de `print()` : `grep -rn "^\s*print(" src/` (exclure tests/)
- [ ] Pas de TODO sans issue : `grep -rn "TODO\|FIXME\|HACK\|XXX" src/`

### 5. Modules obligatoires présents
Vérifier l'existence de chaque fichier critique :
```bash
for f in \
  src/config.py \
  src/feeds/binance_ws.py \
  src/feeds/polymarket_rtds.py \
  src/feeds/polymarket_clob_ws.py \
  src/feeds/feed_manager.py \
  src/signal/delta.py \
  src/signal/gbm.py \
  src/signal/volatility.py \
  src/signal/indicators.py \
  src/signal/scorer.py \
  src/strategy/taker_selective.py \
  src/strategy/kelly.py \
  src/strategy/filters.py \
  src/execution/clob_client.py \
  src/execution/order_builder.py \
  src/execution/slug_resolver.py \
  src/execution/redeemer.py \
  src/engine/clock.py \
  src/engine/loop.py \
  src/engine/state.py \
  src/utils/logger.py \
  src/utils/metrics.py; do
  [ -f "$f" ] && echo "✅ $f" || echo "❌ MANQUANT: $f"
done
```

### 6. Tests correspondants
Pour chaque module `src/x/y.py`, vérifier qu'un `tests/test_y.py` existe :
```bash
for f in src/signal/*.py src/strategy/*.py src/execution/slug_resolver.py; do
  name=$(basename "$f" .py)
  [ "$name" = "__init__" ] && continue
  [ -f "tests/test_${name}.py" ] && echo "✅ test_${name}.py" || echo "❌ MANQUANT: tests/test_${name}.py"
done
```

### 7. Cohérence des constantes
- [ ] Vérifier que `config.py` définit : DELTA_MIN, EDGE_BUFFER, MAX_TOKEN_PRICE, KELLY_FRACTION, STOP_LOSS_PCT
- [ ] Vérifier que les mêmes noms sont utilisés dans `strategy/filters.py` et `strategy/taker_selective.py`

## Format du rapport

```
═══════════════════════════════════════
  RAPPORT DE CONFORMITÉ ARCHITECTURALE
  Date : {date}
═══════════════════════════════════════

1. STRUCTURE     : ✅ OK | ❌ N problèmes
2. SÉCURITÉ      : ✅ OK | ❌ N problèmes
3. DÉPENDANCES   : ✅ OK | ❌ N violations
4. CONVENTIONS   : ✅ OK | ❌ N violations
5. MODULES       : ✅ {N}/22 présents
6. TESTS         : ✅ {N}/{M} couverts
7. CONSTANTES    : ✅ OK | ❌ Incohérences

SCORE GLOBAL : {X}/7 catégories conformes
VERDICT : PRÊT POUR DÉPLOIEMENT | CORRECTIONS NÉCESSAIRES
```

Si des corrections sont nécessaires, liste chaque problème avec le fichier, la ligne, et la correction recommandée.
