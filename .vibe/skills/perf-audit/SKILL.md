---
name: perf-audit
description: Audite le code pour détecter les violations de performance (json au lieu d'orjson, list au lieu de deque, boucles Python au lieu de numpy, etc.)
license: MIT
compatibility: Python 3.11+
user-invocable: true
allowed-tools:
  - read_file
  - grep
  - bash
---

# /perf-audit — Audit de Performance Python

Tu es un auditeur de performance Python spécialisé en systèmes low-latency.

## Ta mission

Scanne l'intégralité du dossier `src/` et identifie TOUTES les violations des règles de performance du projet. Produis un rapport structuré.

## Violations à détecter

### Catégorie CRITIQUE (bloque le déploiement)

1. **JSON standard au lieu d'orjson** :
   - `grep -rn "import json" src/` ou `grep -rn "json.loads\|json.dumps\|json.load\|json.dump" src/`
   - Chaque occurrence est une violation. Le remplacement est `orjson.loads()` / `orjson.dumps()`.

2. **Event loop standard au lieu d'uvloop** :
   - `grep -rn "asyncio.run\|asyncio.get_event_loop" src/`
   - Tout point d'entrée doit utiliser `uvloop.run()`.

3. **Requests bloquant au lieu d'aiohttp** :
   - `grep -rn "import requests\|from requests" src/`
   - Toute I/O HTTP doit être async via `aiohttp`.

4. **print() au lieu de structlog** :
   - `grep -rn "print(" src/` (en excluant les tests et __main__)
   - Utiliser `structlog.get_logger()` partout.

### Catégorie HAUTE (dégrade la performance)

5. **list au lieu de deque pour les buffers temporels** :
   - Chercher des patterns comme `prices = []` suivi de `prices.append()` et `prices.pop(0)` ou `prices = prices[-N:]`
   - Remplacement : `collections.deque(maxlen=N)`

6. **Dataclass sans slots** :
   - `grep -rn "@dataclass" src/` puis vérifier si `slots=True` est présent
   - Chaque `@dataclass` sans `slots=True` est une violation (sauf si héritage nécessaire)

7. **Boucles Python sur des arrays de prix** :
   - Chercher des `for` loops qui itèrent sur des prix/ticks pour calculer des moyennes, écart-types, etc.
   - Remplacement : opérations numpy vectorisées (`np.mean()`, `np.std()`, `np.diff()`)

### Catégorie MOYENNE (amélioration souhaitable)

8. **Type hints manquants** :
   - `bash: mypy --strict src/ 2>&1 | head -50` (si mypy est installé)
   - Sinon, chercher des `def` sans annotation de retour : `grep -rn "def .*):$" src/` (sans `->`)

9. **Fonctions sync dans un contexte async** :
   - `time.sleep()` au lieu de `await asyncio.sleep()`
   - `open()` au lieu de `aiofiles.open()` (si applicable)

## Format du rapport

Pour chaque violation trouvée, affiche :
```
[CRITIQUE|HAUTE|MOYENNE] fichier:ligne — Description
  Code actuel : <la ligne fautive>
  Correction  : <le remplacement recommandé>
```

Termine par un résumé :
```
═══ RÉSUMÉ AUDIT PERFORMANCE ═══
Violations CRITIQUES : N
Violations HAUTES    : N
Violations MOYENNES  : N
Score : X/10 (10 = aucune violation)
```

## Exécution

Lance les commandes `grep` et `bash` nécessaires, lis les fichiers suspects, et produis le rapport complet.
