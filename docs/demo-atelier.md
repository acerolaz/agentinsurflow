# Script de démo : atelier croisé n°2 (2 min + 20 min)

> 🗄️ **Document du sprint 2** (atelier croisé n°2), conservé tel quel : il décrit le socle d'alors (une seule app,
> `POST /api/agent`, `evals-pr` actif). L'état actuel (gateway + rag, `POST /api/reponses`, `evals-pr` désactivé
> jusqu'à U5) est dans le [README](../README.md).

On note **du démontré, jamais du déclaré** (source : grille-atelier-2-socle-chaine.pdf). Chaque minute
montre un critère de la grille sur l'environnement déployé.

Date de l'atelier : `🔴 15/10/2026`.

## Préparation (la veille et 10 min avant)

- [ ] La veille : répétition complète chronométrée, durées notées ci-dessous.
- [ ] La branche `demo/swagger-exemple` est prête : elle change l'exemple du schéma `Question` (visible dans Swagger) **et ajoute un cas à `eval/golden.jsonl`**, pour déclencher les evals. **Sa PR est ouverte et verte**, `evals-pr` compris.
- [ ] La branche `demo/commit-casse` est prête **en local, non poussée** (voir [preuve-blocage.md](preuve-blocage.md)).
- [ ] 10 min avant : réveiller staging et production (`min-replicas 0`) en appelant `/health` sur les deux.
- [ ] Onglets ouverts : Swagger prod · Actions · PR · Settings › Environments · terminal dans le repo.
- [ ] Plan B hors ligne : journaux et captures dans `eval/preuves/`.

## Déroulé

| Temps | Critère | Geste | Ce que l'évaluateur constate |
|---|---|---|---|
| **−2:00 → 0:00** | Journal des retours | Conseil reçu à l'atelier n°1 : `🔴 fourni par Acerola` ; ce qui a été fait ; où le voir | Statut traité / reporté / écarté, avec la preuve |
| **0:00 → 1:30** | — | Le schéma de la chaîne (README) : ce qui bloque, où, et pourquoi | La carte de la démo |
| **1:30 → 4:00** | **1 · Ça tourne ailleurs** | Ouvrir l'URL de production (`https://insurflow-production.redstone-0f3be5e1.swedencentral.azurecontainerapps.io`, Swagger sur `/`) depuis **la machine de l'évaluateur** ; `POST /api/agent` en live ; `GET /health` | `mode: "llm"`, `modele: "Kimi-K2.5"` : le LLM répond. `version` = SHA de `main` (`git rev-parse HEAD`) |
| **4:00 → 5:00** | **2 · Livraison automatique** (lancement) | Merger la PR `demo/swagger-exemple` | Le run `ci-cd` démarre seul, sans action manuelle |
| **5:00 → 6:00** | **3 · Un échec bloque** (lancement) | `git push` de `demo/commit-casse` + `gh pr create --fill` | Un deuxième run démarre en parallèle |
| **6:00 → 10:00** | **5 · Secrets et reproductibilité** (pendant que les runs tournent) | `.gitignore` · `.env.example` sans valeurs · `git ls-files \| grep .env` (vide) · Settings : variables seulement, **aucun secret** (OIDC pour Azure, identité managée pour le LLM) · `make infra` idempotent · [secrets.md](secrets.md) | Aucun secret dans le dépôt ; l'environnement se reconstruit depuis le repo |
| **10:00 → 12:30** | **3 · Un échec bloque** (résultat) | Ouvrir la PR cassée | `lint` ✔, `test` ✘ (2 échecs nommés sur 29), `evals-pr` sauté, merge **bloqué** ; build et déploiement jamais lancés |
| **12:30 → 15:00** | **2 · Livraison automatique** (résultat) | Le run du merge : `changements` détecte le golden dataset modifié → lint → test → build → staging + fumée → **evals** → production + fumée ; ouvrir l'artefact `evals-staging-<sha>` (manifeste : modèle, prompt, golden dataset) | Swagger prod montre le nouvel exemple ; `/health` donne le nouveau SHA, la `release` et le `manifeste` |
| **15:00 → 18:30** | **4 · Rollback** | `make rollback` → run `deploy` → `/health` | Retour au SHA précédent **en une opération**, chrono à l'appui |
| **18:30 → 20:00** | Synthèse | Les 5 critères ↔ leurs preuves (tableau ci-dessous) ; remise en avant : `make rollback` | — |

## Preuves par critère (pour les 15 min de questions)

| # | Critère | Preuve live | Preuve versionnée |
|---|---|---|---|
| 1 | Ça tourne ailleurs | URL de prod depuis la machine de l'évaluateur | Fumée verte dans le journal de `deploy` |
| 2 | Livraison automatique | Run déclenché par le merge | `eval/preuves/livraison-*.log` |
| 3 | Un échec bloque | PR rouge, merge bloqué | `eval/preuves/blocage-*.log` + capture |
| 4 | Rollback | `make rollback`, puis `/health` | `eval/preuves/rollback-*.log` + `.md` |
| 5 | Secrets et reproductibilité | `git ls-files`, Settings, OIDC | `docs/secrets.md`, `.env.example`, `infra/bootstrap.sh` |

## Si ça casse en live

| Incident | Réaction |
|---|---|
| Le modèle Foundry ne répond pas (ou dépasse 30 s) | Montrer `mode: "degrade"` : c'est le repli prévu (K5). La fumée et les evals arrêtent alors la chaîne avant la production, ce qui démontre aussi le critère 3 |
| Démarrage à froid trop long | Montrer staging, déjà réveillé ; la fumée attend jusqu'à 150 s |
| Runner GitHub lent | Passer au critère suivant et y revenir ; plan B : `eval/preuves/` |
