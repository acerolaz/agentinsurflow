# Réactiver `evals-pr` et joindre le rapport d'évaluation à la PR (issue #55, C13)

*Conception du 29/10/2026. Échéance : examen blanc du 30/10.*

## Intention

Le référentiel (C13) attend une chaîne d'intégration continue du modèle **livrée sous forme de PR, avec le rapport d'évaluation attaché**. Aujourd'hui, le job `evals-pr` de `.github/workflows/ci-cd.yml` est coupé (`if: false`) : il démarrait `rag` dans le runner, ce que R6 a rendu impossible (jeton Entra, PostgreSQL, `RAG_SEUIL`, et surtout jeton LLM, voir « Contrainte »). Seules les évaluations contre staging, après merge, tournent.

Demain, devant le jury, Acerola ouvre une PR, lui pose le libellé `evals`, et le jury voit sur la PR : le job `evals-pr` vert, une étape de test des données, et un commentaire qui résume le rapport d'évaluation avec le lien vers l'artefact JSON complet.

## Contrainte qui fixe la forme

`rag` n'obtient son jeton LLM (et d'embeddings) qu'avec `RAG_CLIENT_SECRET` ou une identité managée (`rag/agentinsurflow_rag/infrastructure/entra/application.py:17`, `infrastructure/azure_openai/llm.py:24`) ; un runner GitHub n'a ni l'un ni l'autre, et l'identité de CI ne porte pas le rôle `LLM` exigé par la gateway sur `/api/llm` (`gateway/…/Program.cs:142`, `infra/llm.sh:105`). Un `rag` démarré dans le runner ne peut donc ni ingérer ni répondre avec le vrai LLM sans écriture Entra et sans modifier `rag`.

**Décision d'Acerola** : pour le 30/10, `evals-pr` évalue **l'API de staging** (option 2). Le `rag` local avec le vrai LLM (option 1) est suivi dans #180.

## Objectifs (critères d'acceptance de #55)

1. Étapes, tâches et déclencheurs de la chaîne définis et documentés, tous les déclencheurs disponibles.
2. `evals-pr` s'exécute sur PR sans erreur, en OIDC `pull_request`, contre staging (dont le `rag` a sa base PostgreSQL et son `RAG_SEUIL`).
3. Une étape de **test des données** est intégrée et passe : schéma du golden set et du jeu de démo, intégrité (sha256) de l'instantané Légifrance.
4. Les étapes de test et de validation du modèle sont intégrées et passent : golden set et jeu de démo **de la PR** rejoués contre staging, porte bloquante de `tools/evals.py` (taux de réussite, latence p95).
5. Le rapport d'évaluation est **attaché à la PR** (commentaire + lien d'artefact).
6. Sources de la chaîne versionnées (workflow, outil de test des données, doc).
7. Documentation : installation, configuration et test de la chaîne, et doc utilisateur du déclenchement.

## Limites assumées (à écrire telles quelles dans la doc)

- `evals-pr` évalue le **code de `main` déployé en staging** avec les **jeux d'évaluation de la PR**. Un prompt ou un instantané modifié dans la PR n'est évalué par le modèle qu'après merge, par le job `evals` de staging (porte bloquante avant release, inchangée). Le test des données, lui, porte bien sur les fichiers de la PR.
- Pas de service PostgreSQL dans le job : la base est celle de staging.
- Le critère « service PostgreSQL, `RAG_SEUIL` » de #55 n'est donc couvert qu'à travers staging ; la couverture complète est l'objet de l'issue de suite (option 1).

## Non-objectifs

- Toucher au job `evals` de staging ni à la chaîne de merge (build → staging → release → production).
- Modifier `rag`, la gateway ou les rôles Entra.
- Évaluer le cluster d'agents ou le serveur MCP.

## Anti-objectifs (échec même si « ça marche »)

- **Un secret** dans le dépôt ou dans GitHub.
- **Une écriture Azure ou Entra** : seuls les sujets OIDC déjà fédérés sont utilisés (`pull_request`, `ref:refs/heads/main`).
- Un job `evals-pr` **sauté** sur la PR de démonstration.
- Le jeton d'évaluation dans un log, le rapport ou le commentaire.
- Présenter `evals-pr` comme une évaluation du prompt de la PR : la limite ci-dessus est dite, dans la doc et dans le commentaire.

## Décisions d'Acerola

- **Option 2** : `evals-pr` contre staging ; option 1 dans une issue de suite.
- **Déclenchement forcé par un libellé de PR `evals`**, en plus du filtre existant sur les fichiers déclencheurs (`DECLENCHEURS_EVALS`). Le libellé garde le sujet OIDC `pull_request`.
- **`workflow_dispatch` ajouté** comme déclencheur documenté, qui force les évaluations. Fédéré seulement depuis `main` ; depuis une autre branche la connexion OIDC est refusée : documenté, pas contourné.

## Conception

### Déclencheurs de `ci-cd.yml`

| Événement | Ce qui tourne |
|---|---|
| `pull_request` (`opened`, `synchronize`, `reopened`) | lint → test → `evals-pr` **si** un fichier déclencheur a changé depuis le dernier manifeste validé |
| `pull_request` `labeled` avec le libellé `evals` | `evals-pr` **forcé** |
| `push` sur `main` | chaîne de merge, inchangée |
| `workflow_dispatch` (depuis `main`) | lint → test → `evals-pr` forcé ; rapport en artefact et en résumé du run |

Condition de `evals-pr` : `changements.outputs.evals == 'true'`, **ou** libellé `evals` présent sur la PR, **ou** `workflow_dispatch`.

### Job `evals-pr`

Calqué sur le job `evals` de staging (`ci-cd.yml`, même identité, mêmes options d'`evals.py`) :

1. **Connexion OIDC** (`azure/login`, `allow-no-subscriptions`).
2. **Test des données** (avant tout appel réseau), voir plus bas.
3. **Jeton d'évaluation** : `az account get-access-token --scope api://agentinsurflow-rag/.default`, masqué, en `EVALS_JETON` (la CI porte déjà le rôle Gestionnaire, `infra/entra.sh:116`).
4. **Évaluations** : `tools/evals.py --url "$STAGING_URL" --questions eval/questions-demo.jsonl --sans-dossiers --rapport evals-pr.json`, avec les fichiers de la PR.
5. **Artefact** `evals-pr-<sha>` (toujours, même en échec).
6. **Commentaire sur la PR** (toujours, sur `pull_request` seulement) : taux de réussite, p95, cas et contrôles ratés, manifeste résumé (commit évalué = celui de la PR pour les jeux, version servie par staging lue sur `/health`), la limite en une ligne, lien vers le run et l'artefact. Un seul commentaire par PR, mis à jour à chaque exécution (marqueur HTML caché). Permission `pull-requests: write` sur ce job seulement. Sur `workflow_dispatch`, le même résumé va dans `$GITHUB_STEP_SUMMARY`.

**URL de staging** : nouvelle variable de dépôt `STAGING_URL`, symétrique de `PROD_URL`, posée une fois par Acerola (`gh variable set STAGING_URL --body https://…`, écriture GitHub, pas Azure). Le job échoue avec un message clair si elle est vide. L'environnement GitHub `staging` n'est pas utilisé : il exige une approbation manuelle.

### Test des données

Une étape déterministe, sans réseau, qui échoue avec un message clair si :

- une ligne de `eval/golden.jsonl` ou `eval/questions-demo.jsonl` n'est pas du JSON, n'a pas d'`id` (unique dans le fichier), de `question` non vide, ou a un `attendu` hors du contrat lu par `verifier` (`statut`, `articles`, `http`) ;
- un article attendu par un cas **n'existe pas dans le dernier instantané** `data/raw/code-assurances-*.json` (le cas serait faux d'avance) ;
- l'instantané est altéré : sha256 des articles ≠ `manifeste.sha256`, ou nombre d'articles ≠ `manifeste.articles`. La vérification réutilise la lecture de `rag/agentinsurflow_rag/cli/ingest.py` (`sha_articles`), sans la réécrire.

Les sha256 des fichiers vérifiés sont affichés dans le log et repris dans le manifeste du rapport (déjà fait par `tools/evals.py`). L'étape est appelable en local (cible `make` dédiée). Ses contrôles sont des fonctions pures sur des lignes déjà lues, couvertes par des TU ; la lecture des fichiers reste dans le point d'entrée.

### Documentation

Une page `docs/ci-evals.md`, liée depuis le README racine :

- **Installation et configuration** : variables lues (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `STAGING_URL`), sujets OIDC fédérés et pourquoi `workflow_dispatch` ne marche que depuis `main`, rôle Gestionnaire de la CI, libellé `evals`.
- **Étapes et déclencheurs** : le tableau ci-dessus, avec un schéma de la chaîne PR → merge.
- **Limites** : la section « Limites assumées », et le renvoi vers #180.
- **Test de la chaîne** : test des données et `make eval URL=…` en local ; procédure de démonstration (PR → libellé `evals` → job vert → commentaire).
- **Doc utilisateur du déclenchement** : forcer les évaluations sur une PR, lire le commentaire et le rapport.

## Préalables (Acerola, avant la démo)

- `gh variable set STAGING_URL --body <URL de la gateway de staging>`.
- `gh label create evals` (ou laissé au job : `gh label create … || true` à la première exécution, au choix du constructeur).
- La démo se fait depuis une branche du dépôt (pas un fork : pas de jeton OIDC).

## Laissé au constructeur

- Le nom et l'emplacement de l'outil de test des données (dans `tools/evals.py` ou un outil voisin), sans dupliquer `verifier` ni `sha_articles`.
- La forme du commentaire (tableau Markdown concis) et l'outil pour le poster (`gh` ou `actions/github-script`).
- Le filtrage des événements `labeled` sans rapport avec `evals`.
- La mise à jour des TU qui lisent `ci-cd.yml` (`tests/unit/test_deploy.py`, `tests/unit/test_ci_modele.py`, …) et un test sur la condition d'`evals-pr`.
