# Pipeline d'ingestion

**Rattachement : E1 : C1 Extraction, C3 Agrégation.**

*Livrables L2, L3. Code : `rag/agentinsurflow_rag/cli/ingest.py` (CLI),
`rag/agentinsurflow_rag/infrastructure/legifrance/` (client PISTE), `rag/agentinsurflow_rag/domain/corpus.py`
(nettoyage, découpage), `rag/agentinsurflow_rag/application/use_cases/` (ingestion). Spec §3.*

## Spécifications techniques

| Rubrique | Contenu |
|---|---|
| Technologies | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL 16 + pgvector, `httpx`, Docker ; C# / ASP.NET Core 10 pour `underwriting-admin` et la gateway ; analyseur `html.parser` de la bibliothèque standard (scraping) ; PySpark, Spark SQL, Parquet et Java 17 (big data, groupe uv `bigdata`) |
| Services externes | API Légifrance (PISTE, OAuth 2.0), Azure OpenAI (`text-embedding-3-small`, `gpt-4.1-mini`), Entra ID, OpenML (fichiers ARFF de freMTPL2, sans identifiant) |
| Langages | Python, C#, SQL, YAML (chaîne), JSONL (questions), Bash (`infra/`) |
| Accessibilité | Markdown structuré, schémas doublés d'un texte, messages d'erreur explicites, Swagger UI comme interface |

## Les 10 étapes

| # | Étape | Où | Règle |
|---|---|---|---|
| ① | Lancement | CLI | Configuration + jeton ; un 401 donne « identifiants PISTE invalides » et un code de sortie non nul |
| ② | Extraction | CLI | Plan du code → filtre du périmètre → `getArticle` séquentiel ; 3 nouvelles tentatives à délai croissant sur 429 et 5xx |
| ③ | Sauvegarde brute | CLI | Fichier temporaire puis renommage (jamais d'instantané partiel) ; manifeste versionné |
| ④ | Envoi | CLI | Lots de 50 vers `POST /api/ingestions` par la gateway (rôle `Ingestion`) ; `--instantane <fichier>` saute ① à ③ |
| ⑤ | Validation | `rag` | Structure du lot validée (422 sinon) ; chaque article contrôlé un par un : un article partiel est **rejeté avec sa raison**, le lot continue |
| ⑥ | Nettoyage | `rag` | HTML → texte, NFC, espaces, dates ISO, numéro homogène (`L. 211-1` → `L211-1`) ; rejet des articles vides, trop courts ou non en vigueur, avec leur raison. Montants et durées tels que la loi les écrit |
| ⑦ | Dédoublonnage | `rag` | Même (`doc_id`, hash) → inchangé ; nouveau hash → nouvelle version, l'ancienne passe `obsolete` ; quasi-doublon > 0,95 → **signalé, pas rejeté** |
| ⑧ | Découpage | `rag` | 1 article = 1 chunk ; au-delà d'environ 500 tokens, redécoupage par paragraphes (recouvrement 50) |
| ⑨ | Embeddings | `rag` | Par lot, `run_in_threadpool` ; indisponible → 503 `EMBEDDINGS_INDISPONIBLES` |
| ⑩ | Écriture et fin | `rag` | Une transaction par lot ; **rapport JSON** (lus, insérés, inchangés, versions, rejets avec raison, quasi-doublons, durée) journalisé (table `ingestion`) et versionné dans `eval/preuves/` |

**Idempotence** : rejouer le même instantané donne « 0 inséré » (test E2E `test_ingestion_rejouee_zero_insere`).

## Commandes

```bash
make extraire                                               # ①-③ : Légifrance → data/raw/ (identifiants PISTE du .env)
make ingest URL=http://localhost:8000                       # ①-⑩ : extraction + envoi
make ingest URL=http://localhost:8000 INSTANTANE=data/raw/code-assurances-2026-10-27.json   # ④-⑩ : rejeu
```

## Trois autres chaînes d'extraction

### Notices produits : scraping (#45)

*Code : `tools/scraping_notices.py`. Pages servies par la gateway sous `/notices/`.*

| Étape | Règle |
|---|---|
| Lancement | `make scraper URL=<gateway>` ; `--environnement` et `--date` facultatifs |
| Initialisation | Lit `robots.txt` et respecte ses règles ; User-Agent `AgentInsurFlow-scraping/1.0` |
| Traitement | Page d'index, puis chaque notice, avec 1 s entre deux requêtes ; les méta `doc_id`, `version`, `article` et `date_debut` sont lues dans la page, le corps est converti en texte structuré |
| Contrôle | `tiers`, `tiers_etendu` et `tous_risques` doivent être présentes |
| Sauvegarde | `data/raw/notices-<date>.json` + manifeste SHA-256, par écriture atomique |

| Erreur | Comportement |
|---|---|
| Page interdite par `robots.txt` | Arrêt, code de sortie 1, aucun instantané |
| Statut HTTP autre que 200, ou erreur réseau | Arrêt, code de sortie 1, aucun instantané |
| Méta manquante ou vide | Arrêt avec le nom de la méta et l'URL |
| Notice requise absente | Arrêt avec le nom de la notice |

L'instantané versionné a été produit depuis la production le 02/11/2026 (4 notices). La démonstration le rejoue, sans scraping en direct : `make agreger` lit le dernier `data/raw/notices-*.json`, et le déploiement ingère ce jeu.

### Dossiers : base de données

*Code : `tools/extraction_base.py`. Requête : [`requetes-sql.md`](requetes-sql.md) §7.*

| Étape | Règle |
|---|---|
| Lancement | `make extraire-base`, avec `PG_DOSSIERS_PASSWORD` dans l'environnement ; `PG_HOST` et `PG_PORT` facultatifs |
| Initialisation | Connexion `asyncpg` au compte `dossiers`, délai de 10 s |
| Traitement | Une requête SQL sur `vue_contrat_minimisee` : agrégats par formule et tranche d'âge, jamais de ligne individuelle |
| Sauvegarde | `data/raw/dossiers-agregats-<date>.json` + manifeste SHA-256, par écriture atomique ; connexion toujours fermée |

| Erreur | Comportement |
|---|---|
| Mot de passe absent | Message nommant la variable, code de sortie 1, aucune connexion |
| Base injoignable ou authentification refusée | Message sans le mot de passe, code de sortie 1, aucun instantané |
| Aucun dossier en base | Code de sortie 1, aucun instantané |

### freMTPL2 : big data (#51)

*Code : `tools/extraction_bigdata.py`. Requêtes : [`requetes-sql.md`](requetes-sql.md) §6.*

| Étape | Règle |
|---|---|
| Lancement | `make bigdata [ARGS=--expliquer]`, Java 17 requis |
| Initialisation | Session Spark locale ; téléchargement des ARFF d'OpenML en cache, SHA-256 vérifiées (`fonction-calcul/entrainement/donnees.toml`) |
| Traitement | ARFF → Parquet → 2 requêtes Spark SQL : fréquence par région, coût moyen par tranche de bonus-malus (jointure `BROADCAST`) |
| Sauvegarde | `data/raw/fremtpl2-agregats-<date>.json` (25 lignes) + manifeste ; session Spark toujours arrêtée |

| Erreur | Comportement |
|---|---|
| Java absent ou mauvaise version | Message explicite, code de sortie 1 |
| SHA-256 différente ou fichier illisible | Arrêt, code de sortie 1, aucun instantané |
| Erreur Spark | Arrêt, code de sortie 1, aucun instantané |

En CI, le déploiement réagrège puis réingère le jeu à chaque déploiement (la base annexe repart vide), avec un jeton
OIDC de la CI (voir « Agrégation (#52) »).

## Gestion des erreurs

| Cas | Comportement |
|---|---|
| Identifiants PISTE invalides | Message clair, code de sortie non nul |
| 429 / 5xx de Légifrance | 3 nouvelles tentatives à délai croissant, puis échec |
| Article partiel ou invalide | Rejeté avec sa raison, compté dans le rapport, le lot continue |
| Échec d'un lot (base, embeddings) | Transaction annulée pour ce lot, code de sortie non nul |
| Jeton absent ou sans rôle `Ingestion` | 401 / 403 à la gateway, ProblemDetails `NON_AUTHENTIFIE` / `ACCES_REFUSE` |
| Jeu agrégé altéré, collection manquante ou barème altéré | Refus avant tout envoi, code de sortie non nul |

## Agrégation (#52)

*Code : `rag/agentinsurflow_rag/cli/agreger.py` (CLI), `rag/agentinsurflow_rag/domain/procedures.py` (procédures
générées), `fonction-calcul/agentinsurflow_calcul/domain/bareme.py` (table `REGLES`) et `instantane.py` (instantané).*

Un **jeu unique** réunit les cinq sources du projet. Avant l'envoi, ce qui est ingéré est exactement la section `entrees` versionnée.

### Spécifications techniques

| Rubrique | Contenu |
|---|---|
| Entrées | Instantané Légifrance (`data/raw/code-assurances-*.json`), instantané du barème (`data/raw/bareme-*.json`), instantané des notices scrapées (`data/raw/notices-*.json`), parties rédigées des procédures (`rag/corpus/procedures_internes/`), agrégats freMTPL2 (`data/raw/fremtpl2-agregats-*.json`) et des dossiers (`data/raw/dossiers-agregats-*.json`) |
| Sortie | `data/aggregated/corpus-<date Légifrance>.json`, octet pour octet identique à chaque relance (aucune date du jour) |
| Schéma d'une entrée | `doc_id`, `version`, `article`, `date_debut` (ISO), `etat` (majuscules), `texte_html`, `url_source`, `regle_id`, `collection`, `source` |
| Schéma d'une statistique | `source`, `indicateur`, `dimensions` (champs descriptifs), `mesures` (champs numériques) ; une ligne sans mesure ou sans dimension arrête l'agrégation |
| Manifeste | `date`, `entrees`, `par_collection`, `par_source`, `sources` (sha256 des cinq instantanés), `ecarts` (`doc_id`, `source`, `raison`), `sha256` des entrées, `statistiques` (`lignes`, `par_source`, `sha256`) |
| Dépendances | Aucune nouvelle (stdlib et code existant) ; fonctionne sans réseau ni identifiants |
| Volumétrie actuelle | 129 entrées : 119 `legifrance`, 4 `scraping`, 6 `bareme` ; 0 écart. 30 statistiques : 25 `fremtpl2`, 5 `dossiers` |

### Deux sections dans le même jeu

| Section | Sources | Usage |
|---|---|---|
| `entrees` | Légifrance, notices scrapées, procédures du barème | Corpus citable : **seule section ingérée** dans le RAG |
| `statistiques` | Agrégats freMTPL2, agrégats des dossiers | Analyse du portefeuille et de la sinistralité : l'agent ne les cite jamais, et aucune ligne individuelle n'y figure |

Les statistiques ne sont pas ingérées, car ce ne sont pas des textes que l'agent peut citer. Les dossiers eux-mêmes restent lus par la vue minimisée et l'outil MCP, sous contrôle du gestionnaire.

### Règles par source

| Source | Origine | Collection |
|---|---|---|
| `legifrance` | Instantané du Code des assurances | `textes_reglementaires` |
| `scraping` | Instantané des notices produits scrapées | `notices_produits` |
| `bareme` | Une procédure par règle : en-tête, titre et section « Règle » **générés** depuis `REGLES`, section « Pièces à vérifier » rédigée (marqueur `{version_bareme}` remplacé) | `procedures_internes` |

La version du barème (`bareme-2026.10-v1`) est citable dans chaque procédure, et le texte de la règle ne peut pas
diverger du code qui l'applique (garde-fou GF5).

### Choix de nettoyage et d'homogénéisation

| Choix | Règle |
|---|---|
| Entrée corrompue = écartée avec sa raison (`ecarts`) | Partielle (champ manquant, état absent), texte vide, texte de moins de 20 caractères, date invalide |
| Abrogés | **Gardés** dans le jeu (état `ABROGE`) ; le serveur les filtre à l'ingestion |
| Doublons | Détectés sur (`doc_id`, `version`) : `A211-1-3` existe en deux versions, c'est légitime ; un même couple deux fois fait échouer l'agrégation |
| Dates | ISO `AAAA-MM-JJ` |
| Numéros | Normalisés (`L. 211-1` → `L211-1`) |
| État | En majuscules |
| HTML et Markdown | Gardés tels quels : le serveur les convertit par `html_vers_texte` |
| Intégrité | Les sha256 des instantanés sont vérifiés avant lecture ; un instantané altéré arrête l'agrégation |

Le nettoyage réutilise `nettoyer` du serveur (état forcé à `VIGUEUR` pour ne pas écarter les abrogés, état d'origine rétabli).

### Commandes et enchaînement

```bash
make bareme                                       # table REGLES → data/raw/bareme-2026.10-v1.json
make agreger                                      # instantanés + rédigés → data/aggregated/corpus-<date>.json
make ingest URL=http://localhost:8000 JEU=data/aggregated/corpus-2026-10-27.json
```

```text
REGLES (bareme.py) → make bareme → instantané du barème ─┐
Légifrance → make extraire → instantané ─────────────────┤
notices → make scraper → instantané ─────────────────────┼→ make agreger → jeu agrégé → make ingest JEU=…
parties rédigées des procédures ─────────────────────────┘
```

`make ingest JEU=…` vérifie le sha256 du jeu, refuse un jeu où manque une collection, envoie chaque collection par
lots de 50 et écrit un fichier de preuve par collection (mode `jeu`). `--source` est refusé pour
`procedures_internes` : passer par `make agreger` puis `make ingest JEU=…`. Au déploiement, `make agreger` est rejoué
et le job échoue si `data/aggregated/` diffère du dépôt (à relancer : `make bareme && make agreger`, puis versionner).

### Modèle de données

Le **modèle Merise est inchangé** : `regle_id` est déjà stocké (migration `0003_regle_id`), l'agrégation ne crée ni
table ni colonne.
