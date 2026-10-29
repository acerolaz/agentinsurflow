# Pipeline d'ingestion

*Livrables L2, L3 · compétences C1, C3. Code : `rag/agentinsurflow_rag/cli/ingest.py` (CLI),
`rag/agentinsurflow_rag/infrastructure/legifrance/` (client PISTE), `rag/agentinsurflow_rag/domain/corpus.py`
(nettoyage, découpage), `rag/agentinsurflow_rag/application/use_cases/` (ingestion). Spec §3.*

## Spécifications techniques

| Rubrique | Contenu |
|---|---|
| Technologies | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL 16 + pgvector, `httpx`, Docker ; C# / ASP.NET Core 10 pour `underwriting-admin` et la gateway |
| Services externes | API Légifrance (PISTE, OAuth 2.0), Azure OpenAI (`text-embedding-3-small`, Kimi-K2.5), Entra ID |
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

Un **jeu unique** réunit les trois collections avant l'envoi : ce qui est ingéré est exactement ce qui est versionné.

### Spécifications techniques

| Rubrique | Contenu |
|---|---|
| Entrées | Instantané Légifrance (`data/raw/code-assurances-*.json`), instantané du barème (`data/raw/bareme-*.json`), notices (`rag/corpus/notices_produits/`), parties rédigées des procédures (`rag/corpus/procedures_internes/`) |
| Sortie | `data/aggregated/corpus-<date Légifrance>.json`, octet pour octet identique à chaque relance (aucune date du jour) |
| Schéma d'une entrée | `doc_id`, `version`, `article`, `date_debut` (ISO), `etat` (majuscules), `texte_html`, `url_source`, `regle_id`, `collection`, `source` |
| Manifeste | `date`, `entrees`, `par_collection`, `par_source`, `sources` (sha256 de l'instantané Légifrance et du barème), `ecarts` (`doc_id`, `source`, `raison`), `sha256` du jeu |
| Dépendances | Aucune nouvelle (stdlib et code existant) ; fonctionne sans réseau ni identifiants |
| Volumétrie actuelle | 129 entrées : 119 `legifrance`, 4 `redige`, 6 `bareme` ; 0 écart |

### Règles par source

| Source | Origine | Collection |
|---|---|---|
| `legifrance` | Instantané du Code des assurances | `textes_reglementaires` |
| `redige` | Notices produits rédigées | `notices_produits` |
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
| Intégrité | Le sha256 du barème est vérifié avant lecture ; un instantané altéré arrête l'agrégation |

Le nettoyage réutilise `nettoyer` du serveur (état forcé à `VIGUEUR` pour ne pas écarter les abrogés, état d'origine rétabli).

### Commandes et enchaînement

```bash
make bareme                                       # table REGLES → data/raw/bareme-2026.10-v1.json
make agreger                                      # instantanés + rédigés → data/aggregated/corpus-<date>.json
make ingest URL=http://localhost:8000 JEU=data/aggregated/corpus-2026-10-27.json
```

```text
REGLES (bareme.py) → make bareme → instantané du barème ─┐
Légifrance → make extraire → instantané ─────────────────┼→ make agreger → jeu agrégé → make ingest JEU=…
notices + parties rédigées des procédures ───────────────┘
```

`make ingest JEU=…` vérifie le sha256 du jeu, refuse un jeu où manque une collection, envoie chaque collection par
lots de 50 et écrit un fichier de preuve par collection (mode `jeu`). `--source` est refusé pour
`procedures_internes` : passer par `make agreger` puis `make ingest JEU=…`. Au déploiement, `make agreger` est rejoué
et le job échoue si `data/aggregated/` diffère du dépôt (à relancer : `make bareme && make agreger`, puis versionner).

### Modèle de données

Le **modèle Merise est inchangé** : `regle_id` est déjà stocké (migration `0003_regle_id`), l'agrégation ne crée ni
table ni colonne.
