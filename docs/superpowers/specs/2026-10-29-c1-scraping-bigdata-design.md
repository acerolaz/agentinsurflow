# C1 / C2 — scraping des notices (#45) et big data PySpark (#51)

*29/10, pour l'examen blanc du 30/10. Issues #45 et #51, compétences C1 et C2.*

## Intention

Le référentiel exige que la collecte combine au minimum ces sources : **API REST, fichier, scraping, base de données et système big data**. Aujourd'hui, `docs/donnees/sources.md` en couvre trois : l'API Légifrance, l'instantané JSON et la base `dossiers`. Le scraping et le big data y sont « reportés au rapport de certification ». Ce chantier ajoute les deux sources qui manquent. Il doit aussi pouvoir se montrer au jury demain, sans risque.

## Décisions d'Acerola

- **Big data = PySpark en local**, sur freMTPL2 au format Parquet. C'est plus simple pour demain. Cette décision remplace l'ADR-06, qui prévoyait Parquet sur ADLS Gen2 : aucune ressource Azure n'est créée.
- **La page scrapée est servie par la gateway**, sur le modèle de l'espace gestionnaire (`wwwroot/app` sous `/app/`).
- **Démo** : on montre au jury **l'instantané versionné et son manifeste**. Le script n'est pas lancé en direct.
- **L'instantané des notices est scrapé sur la gateway de production** : `url_source` est l'URL publique de prod. Cela impose deux PR. La **PR 1** ajoute les pages, `robots.txt`, le script et le support `--instantane --collection` d'`ingest`. Elle laisse `deploy.yml` sur les Markdown, puis elle est déployée. On scrape ensuite la prod. La **PR 2** versionne `notices-<date>.json` et son manifeste, bascule `deploy.yml` sur l'instantané et supprime les Markdown. Avant le déploiement, le script se teste contre la gateway locale (`make up`).
- **Java** : Claude installe `openjdk@17` sur le poste (`brew install openjdk@17`), avec l'accord d'Acerola du 29/10. Les agrégats Spark sont produits sur le poste puis versionnés.
- (Commentaire de l'issue #45) Le script produit les **mêmes `doc_id`** pour que GF6 reste satisfait. L'instantané scrapé **remplace** l'ingestion Markdown dans `deploy.yml` : il n'y a qu'**une seule source par notice**.

## Objectifs

### #45 — Scraping

1. **Les pages sources.** `gateway/src/AgentInsurFlow.Gateway.Api/wwwroot/notices/` est servi sous `/notices/`. Le dossier contient une page d'index qui liste les formules (un lien par notice) et une page HTML par notice : `tiers`, `tiers_etendu`, `tous_risques` et `jeunes_conducteurs` *(décision de Claude : le Gestionnaire ingère aujourd'hui les 4)*. Le contenu reprend les Markdown actuels de `rag/corpus/notices_produits/`. Les métadonnées `doc_id`, `version`, `article` et `date_debut` sont portées dans le HTML, sous une forme facile à extraire. Le choix entre balises `<meta>` et attributs `data-*` revient au builder.
2. **Des contraintes réelles** *(décision de Claude)*. La gateway sert un `/robots.txt` qui autorise `/notices/` et interdit `/api/`. Elle sert aussi une page `/notices/conditions.html` qui précise que les documents sont fictifs, que le projet en détient les droits et que la réutilisation est limitée au projet. Le script lit le robots.txt et le respecte (`urllib.robotparser`, bibliothèque standard). Il s'identifie par un User-Agent explicite et laisse un délai entre deux requêtes. `sources.md` décrit ces contraintes comme des contraintes appliquées, pas seulement déclarées.
3. **Le script `tools/scraping_notices.py`.** Il comprend, dans l'ordre du référentiel :
   - un point de lancement `main()` / `__main__` qui prend `--url` (la base de la gateway) et `--sortie` (par défaut `data/raw/`) ;
   - l'initialisation : client `httpx` (déjà dépendance), robots.txt ;
   - les règles de traitement : lire l'index, suivre chaque lien, parser (avec `html.parser` de la bibliothèque standard, sans nouvelle dépendance — *décision de Claude*), nettoyer, puis produire un document par `doc_id` avec `url_source` (l'URL de la page) et la date d'extraction ;
   - la gestion des erreurs : réseau, statut HTTP, page interdite par robots.txt, HTML sans les métadonnées attendues. Le script s'arrête en erreur (code de sortie non nul) si l'une des notices `tiers`, `tiers_etendu` ou `tous_risques` manque ;
   - la fin du traitement : un résumé (nombre de notices, chemin de l'instantané) ;
   - la sauvegarde : `data/raw/notices-<date>.json` plus le manifeste SHA-256, **au même format que l'instantané Légifrance**. Il faut réutiliser `sauvegarder_instantane()` et `sha_articles()` de `rag/agentinsurflow_rag/cli/ingest.py`, ne pas les réécrire.
4. **Ingestion.** `ingest` sait rejouer un instantané `notices-*.json` dans la collection `notices_produits`. Aujourd'hui, `--instantane` ne vise que `textes_reglementaires`, et `--source` lit les Markdown. Dans `deploy.yml`, la ligne `make ingest … COLLECTION=notices_produits SOURCE=rag/corpus/notices_produits` est remplacée par le rejeu du dernier `notices-*.json`.
5. **Suppression des Markdown** de `rag/corpus/notices_produits/`, une fois l'instantané versionné et l'ingestion basculée. `procedures_internes` reste en Markdown : ce n'est pas dans le périmètre.

### #51 — Fichier et big data

6. **Le fichier.** Le script lit freMTPL2 depuis le fichier téléchargé. Il faut réutiliser `telecharger()` de `fonction-calcul/entrainement/donnees.py` (OpenML 41214, CC0, SHA-256 figé dans `donnees.toml`, cache `FREMTPL2_CACHE`), sans écrire un second téléchargement. Pour la jointure, la table des sinistres freMTPL2sev (OpenML 41215) est ajoutée au même mécanisme, avec sa propre SHA-256 figée.
7. **Le big data.** `tools/extraction_bigdata.py` suit la même structure que le script de scraping (lancement, initialisation, traitement, erreurs, fin, sauvegarde). Il :
   - ouvre une `SparkSession` locale ;
   - convertit freq et sev en Parquet dans le cache, sans versionner ces fichiers ;
   - exécute des requêtes **Spark SQL** : au moins une **jointure** freq × sev sur `IDpol`, des **filtres** (exposition > 0, valeurs dans les bornes déjà fixées par `donnees.py`) et des **agrégats** (fréquence et coût moyen par région, par tranche de bonus-malus) ;
   - sauvegarde le résultat (agrégats, de petite taille) dans `data/raw/fremtpl2-agregats-<date>.json` avec son manifeste SHA-256, et versionne ce résultat.
8. **Documentation C2.** Dans `docs/donnees/requetes-sql.md`, une section Spark SQL *(décision de Claude : le fichier existe déjà pour le SGBD)*. Pour chaque requête : l'objectif de collecte, les sélections, les filtres, les conditions et les jointures. Elle documente aussi les optimisations appliquées, avec la sortie d'`EXPLAIN` comme preuve : format colonnes Parquet, élagage de colonnes, filtres poussés à la lecture (*predicate pushdown*), diffusion de la petite table dans la jointure si elle s'applique.

### Documentation commune

9. `docs/donnees/sources.md` : deux colonnes sont ajoutées, **Pages notices (scraping)** et **freMTPL2 (fichier + big data)**. Chacune indique l'origine, le contenu, le format, la licence (CC0 pour freMTPL2), les données personnelles, les contraintes et le rôle. La mention « Reportés au rapport de certification » est retirée. `docs/donnees/pipeline.md` décrit les deux nouvelles chaînes.

## Critères d'acceptance

Ce sont ceux des issues #45 et #51, qui reprennent le référentiel. En résumé :
- les 3 notices et les agrégats Spark sont effectivement présents dans les instantanés versionnés ;
- chaque script comprend les 6 parties exigées ;
- les scripts sont versionnés ;
- les contraintes de la source sont documentées ;
- les requêtes Spark SQL fonctionnent et sont documentées, optimisations comprises ;
- `sources.md` inventorie les 5 sources.

Après déploiement, le Rédacteur continue de citer la notice du `contrat_type` : **GF6 reste vert**.

## Non-objectifs

- L'agrégation des sources (#52, C3) : les sorties sont seulement prêtes pour elle.
- Faire passer le GLM (O7) par Spark : l'entraînement reste en pandas.
- ADLS Gen2, ou toute ressource Azure nouvelle.
- Scraper de vrais assureurs (AXA, MAIF…), idée des specs initiales abandonnée.
- Lancer le scraping ou Spark dans la CI ou à chaque déploiement : les deux instantanés sont produits sur le poste puis versionnés.

## Anti-objectifs (échec même si « ça marche »)

- Des `doc_id` qui changent, ou une notice absente de `notices_produits` après déploiement : GF6 casse en démo.
- Deux sources vivantes pour une même notice (HTML et Markdown).
- Plusieurs dizaines de Mo de données brutes freMTPL2 commitées.
- La CSP ou l'authentification de la gateway affaiblies pour servir les pages : `/notices/` est public et en lecture seule, comme `/app/`, rien de plus.
- Un second téléchargement freMTPL2 qui ignore la SHA-256 figée.

## Contraintes

- Échéance : examen blanc du 30/10.
- PySpark exige un **Java** (JRE 17 ou plus). Il n'est **pas installé sur le poste** aujourd'hui.
- `pyspark` ne doit pas alourdir les images ni le job `test` de la CI. Il va dans un groupe de dépendances `uv` à part (`bigdata`) *(décision de Claude)*.
- Python : style des scripts de `tools/` (comme `evals.py`), une fonction par partie du traitement. Ce sont des scripts de collecte sans domaine métier : pas de paquet hexagonal *(décision de Claude)*.
- Tests : le parsing des notices est testé sur les fichiers réels de `wwwroot/notices/` (les 3 `doc_id` sont extraits ; un HTML sans métadonnées lève une erreur). La gateway a un test qui vérifie que `/notices/` et `/robots.txt` répondent 200 sans jeton. La requête Spark a un test sur un petit Parquet, à ignorer si Java est absent.

## Précisions après relecture *(décisions de Claude)*

- **`version` inchangée** (`tiers-2026.10-v1`…). La base annexe repart vide à chaque déploiement (`deploy.yml`, étape Corpus) : un texte scrapé légèrement différent du Markdown ne crée aucun conflit. Le corps scrapé reprend les sections du Markdown. GF6 ne dépend que de `doc_id`.
- **`sauvegarder_instantane()`** reçoit un paramètre de préfixe : `code-assurances` reste la valeur par défaut, et les notices utilisent `notices`. Le `perimetre` du manifeste vaut `notices_produits`. C'est une extension, sans réécriture.
- **Ingestion** : `ingest --instantane data/raw/notices-<date>.json --collection notices_produits`. La règle de `_instantane` est assouplie : `--instantane` est accepté avec n'importe quelle collection, et `--source` reste réservé aux Markdown. Dans le `Makefile`, la cible `ingest` passe `COLLECTION` aussi avec `INSTANTANE`.
- **freMTPL2sev** : un second bloc `[source_sev]` dans `donnees.toml`, avec son URL OpenML (41215) et une SHA-256 mesurée une fois. `telecharger()` prend le bloc en paramètre, et le bloc freq reste la valeur par défaut, pour que le GLM et le cache de la CI restent inchangés.
- **Gateway** : `/notices/` et `/robots.txt` sont servis **avant** l'authentification, comme `/app/`, et sous la même CSP. `/robots.txt` est un fichier précis, il ne gêne pas Swagger à la racine.

## Laissé au builder

- La forme des métadonnées dans le HTML et la mise en page des notices (sobre, sans JS).
- La conversion ARFF → Parquet : pandas puis Spark, ou lecture directe par Spark.
- Le découpage exact en PR et l'ordre des étapes, dans le respect de l'anti-objectif GF6.
