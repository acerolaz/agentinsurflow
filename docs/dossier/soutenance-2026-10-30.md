# Soutenance du 30/10 — E1 (C1 à C5) et E3 (C9 à C13) : critère → preuve

*État de `main` au 29/10 (v0.6.24 en production, `ci-cd` vert sauf `pyramide`, non bloquant). Démo : scénario
« générer un contrat » de la préparation du 27/10 ; ce tableau sert si le jury creuse.*

✅ preuve en place · 🟡 partielle ou écart assumé · ❌ manque

## E1 — Données (rapport 2 à 5 pages, 15 min)

| Critère | État | Preuve à citer |
|---|---|---|
| C1 · Présentation du projet (acteurs, objectifs, contraintes, budget, planning) | ✅ | Dossier de conception (`specs/` du dossier de certification, hors dépôt), backlog d'octobre |
| C1 · Spécifications techniques de l'extraction et de l'agrégation | ✅ | [`donnees/pipeline.md`](../donnees/pipeline.md) (10 étapes), [`donnees/sources.md`](../donnees/sources.md) |
| C1 · Script fonctionnel et structuré (lancement, connexions, erreurs, sauvegarde) | ✅ | `rag/agentinsurflow_rag/cli/ingest.py`, client `infrastructure/legifrance/client.py` ; rapports `eval/preuves/ingestion-2026-10-27-{staging,production}.json` |
| C1 · Mix API REST, fichier, scraping, base de données, big data | 🟡 | API Légifrance, instantané JSON, base `dossiers`, documents rédigés. **Scraping (#45) et big data (#51) non faits** : écart justifié dans `sources.md` (API officielle sous licence ouverte ; quelques centaines d'articles) |
| C2 · Requêtes SQL documentées (sélection, filtres, jointures) | ✅ | [`donnees/requetes-sql.md`](../donnees/requetes-sql.md) § 1 à 3 |
| C2 · Optimisations documentées | 🟡 | Index HNSW / IVFFlat / scan exact (§ 4), `EXPLAIN ANALYZE` de la vue minimisée (§ 5) ; recherche vectorielle pas encore mesurée |
| C3 · Agrégation, nettoyage, normalisation | 🟡 | Étapes de nettoyage du pipeline, `data/raw/` + manifeste sha256. **Fusion en un jeu unique (#52) et barème citable (#99) non faits** |
| C4 · Merise, MPD, choix du SGBD, installation | ✅ | [`donnees/modele.md`](../donnees/modele.md) (MCD avec la mémoire du cluster et les relances, MPD, PostgreSQL 16 + pgvector, installation pas à pas) |
| C4 · Script d'import | ✅ | `make extraire` puis `make ingest`, réingestion par `deploy.yml` |
| C4 · Registre RGPD et procédures de tri (traitements, fréquences) | ✅ | [`donnees/rgpd.md`](../donnees/rgpd.md) : durées proposées le 29/10 (#53), purge des spans à 30 jours |
| C5 · API documentée, standard, authentifiée, accès restreint | ✅ | Swagger unique de la gateway (`docs/openapi/`), jetons Entra, BOLA : dossier de B → 404 (démo, séquence 11:00) |

## E3 — Modèle d'IA (rapport 15 à 20 pages, 20 min dont démo)

| Critère | État | Preuve à citer |
|---|---|---|
| C9 · API du modèle, authentification, OWASP | ✅ | `agentic-cluster/agentinsurflow_cluster/api/routes.py` (lancer, pause, reprise), revue humaine, contrat généré ; même 404 qu'un dossier inexistant |
| C9 · Tests de tous les points de terminaison | ✅ | TI du cluster et d'`underwriting-admin`, E2E en staging (job `e2e-staging`) |
| C10 · Application qui consomme l'API | ✅ | Espace `/app/` (`gateway/.../wwwroot/app/`), [`espace-gestionnaire.md`](../espace-gestionnaire.md), PR #134 ; tests `gateway/tests/espace/` |
| C10 · Accessibilité | 🟡 | Parcours au clavier (K6) joué en staging, à revérifier après #147 |
| C11 · Métriques, outils, alertes, restitution | 🟡 | [`observabilite-app-insights.md`](../observabilite-app-insights.md), tableaux de bord `vigie-staging` / `vigie-production`, alertes AL-6/8/9 ; **aucune évaluation réelle encore visible dans Application Insights (#176)**, #54 en cours |
| C12 · Cas de test, outils, seuils | ✅ | `eval/golden.jsonl`, garde-fous `eval/garde-fous/` ; évals du 27/10 : 100 %, p95 14,9 s (`eval/preuves/evals-2026-10-27.json`) ; GLM de fréquence entraîné et évalué (`make modele`, job `modele`) |
| C12 · Pyramide de tests | 🟡 | Job `pyramide` rouge : TU 57 % (seuil 65 %), TI 40 % (plafond 25 %) ; non bloquant, à expliquer (#48) |
| C13 · Chaîne de livraison continue | ✅ | `.github/workflows/ci-cd.yml` : lint → tests → `modele` → build → staging → `evals` → E2E → release → production sur approbation |
| C13 · Évaluation du modèle à chaque PR | 🟡 | `evals` ne tourne que si `DECLENCHEURS_EVALS` change (prompts, golden, `data/raw/`) ; `evals-pr` désactivé (#55) |

## Écarts à annoncer avant que le jury les trouve

1. C1 : scraping et big data reportés, avec la raison écrite dans `sources.md`.
2. C3 : pas de jeu de données unique issu de la fusion des sources (#52).
3. C11 : la chaîne est en place mais n'a pas encore vu de trafic authentifié (#176) ; lancer une évaluation en
   production avant la soutenance règle ce point.
4. C12 : pyramide hors seuils, assumée (beaucoup de TI sur les frontières de sécurité).
