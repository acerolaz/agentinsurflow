# Requêtes SQL — recherche hybride, dossiers, traces

*Livrable L5 · compétence C2. Sources : `rag/agentinsurflow_rag/infrastructure/postgres/corpus.py`
(`SQL_HYBRIDE`, `SQL_PAR_ARTICLES`), `underwriting-admin/…/Dossiers/VueMinimisee.cs` et `DepotDossiersEf.cs`,
`underwriting-admin/…/Traces/DepotTracesEf.cs`. Tout le SQL est paramétré (`:param` côté SQLAlchemy,
interpolation paramétrée côté EF Core) : aucune valeur n'est concaténée.*

## 1. Recherche hybride (`rag`, compte `reader`)

Deux classements, vectoriel (cosinus, HNSW) et plein texte (`websearch_to_tsquery`, `ts_rank_cd`, GIN),
filtrés par collection et `NOT obsolete`, fusionnés par **RRF** (k = 60). Le score RRF ne sert qu'à ordonner ;
la porte de pertinence utilise le cosinus (`RAG_SEUIL`).

```sql
WITH vect AS (                                    -- sélection + filtre + tri vectoriel (HNSW)
    SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> CAST(:v AS vector)) AS rang
    FROM chunk c JOIN document d ON d.id = c.document_id
    WHERE NOT d.obsolete AND d.collection = ANY(:collections)
    ORDER BY c.embedding <=> CAST(:v AS vector)
    LIMIT :candidats
), plein_texte AS (                               -- plein texte (GIN sur tsv)
    SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q) DESC) AS rang
    FROM chunk c JOIN document d ON d.id = c.document_id,
         websearch_to_tsquery('french', :question) q
    WHERE NOT d.obsolete AND d.collection = ANY(:collections) AND c.tsv @@ q
    ORDER BY ts_rank_cd(c.tsv, q) DESC
    LIMIT :candidats
), fusion AS (                                    -- agrégat : Σ 1 / (60 + rang)
    SELECT id, sum(1.0 / (60 + rang)) AS score
    FROM (SELECT id, rang FROM vect UNION ALL SELECT id, rang FROM plein_texte) classements
    GROUP BY id
)
SELECT c.id AS chunk_id, c.article, c.texte, d.doc_id, d.version, d.collection,
       d.date_debut, d.url_source, f.score AS score_rrf,
       1 - (c.embedding <=> CAST(:v AS vector)) AS cosinus
FROM fusion f JOIN chunk c ON c.id = f.id JOIN document d ON d.id = c.document_id
ORDER BY f.score DESC, c.id
LIMIT :k;
```

**Référence exacte** (la question cite `L211-1`, `R211-3`…) : recherche directe sur `chunk.article` (B-tree) :

```sql
SELECT c.id AS chunk_id, c.article, c.texte, d.doc_id, d.version, d.collection, d.date_debut, d.url_source
FROM chunk c JOIN document d ON d.id = c.document_id
WHERE NOT d.obsolete AND d.collection = ANY(:collections) AND c.article = ANY(:articles)
ORDER BY array_position(CAST(:articles AS text[]), c.article), c.ordre;
```

## 2. Dossiers (`underwriting-admin`, compte `dossiers`)

Lecture **uniquement** par la vue minimisée, toujours filtrée par le gestionnaire connecté (BOLA) :

```sql
SELECT * FROM vue_contrat_minimisee
WHERE gestionnaire_id = :oid AND numero_contrat = :numero;          -- un contrat
SELECT * FROM vue_contrat_minimisee
WHERE gestionnaire_id = :oid ORDER BY numero_contrat LIMIT :limit OFFSET :offset;  -- portefeuille
```

La vue elle-même fait les jointures (`contrat` ⨝ `souscripteur` ⟕ `releve_information`) et l'agrégat
(nombre de sinistres) : voir [`modele.md`](modele.md).

## 3. Traces (`underwriting-admin`)

Insertion idempotente (`INSERT … ON CONFLICT DO NOTHING`, compte `traces_writer`) ; relecture d'une trace
(`WHERE trace_id = :id ORDER BY start_time_unix_nano`, compte `traces_reader`). Requêtes d'analyse :
[`traces.md`](traces.md).

## 4. Index et comparatif HNSW / IVFFlat / scan exact

| Index | Table · colonne | Sert à |
|---|---|---|
| HNSW `vector_cosine_ops` | `chunk.embedding` | Tri vectoriel approché |
| GIN | `chunk.tsv` | Plein texte (`@@`) |
| B-tree | `chunk.article`, `chunk.document_id` | Référence exacte, jointure |
| B-tree partiel | `document.collection` WHERE NOT `obsolete` | Filtre de collection |
| UNIQUE `ix_contrat_numero_contrat` | `contrat.numero_contrat` | Clé pivot, lookup d'un contrat |
| B-tree | `contrat.gestionnaire_id` | Portefeuille (BOLA) |
| B-tree, GIN | `span` (`service_name`, `start_time_unix_nano`), `attributes` | Analyse des traces |

| Méthode | Construction | Rappel | Quand |
|---|---|---|---|
| Scan exact | Aucune | 100 % (référence) | Petits volumes ; mesure de référence du rappel |
| IVFFlat | Exige des données présentes pour entraîner les listes | Dépend de `lists` / `probes` | Gros volumes stables |
| **HNSW** (retenu) | Incrémentale, sans entraînement | Élevé, réglable (`ef_search`) | Corpus qui grandit par ingestions successives |

## 5. Mesures `EXPLAIN ANALYZE`

### Vue minimisée — mesurée le 21/10/2026 sur la base locale (6 contrats, 2 gestionnaires)

Contrat existant, lu par son propre gestionnaire (`AIF-2026-000001`) :

```text
Nested Loop Left Join  (actual time=6.018..6.020 rows=1 loops=1)
  ->  Nested Loop  (rows=1)
        ->  Index Scan using ix_contrat_numero_contrat on contrat c  (rows=1)
              Index Cond: (numero_contrat = 'AIF-2026-000001'::text)
        ->  Index Scan using pk_souscripteur on souscripteur s  (rows=1)
  ->  Index Scan using ix_releve_information_contrat_id on releve_information r  (rows=1)
  SubPlan -> Aggregate -> Bitmap Heap Scan on sinistre si
Planning Time: 0.564 ms
Execution Time: 0.100 ms
```

Le contrat est trouvé par l'index unique, puis filtré par gestionnaire (`gestionnaire_id = :oid`) : pour un
contrat d'un autre gestionnaire, le même plan ne renvoie aucune ligne (même 404 qu'un contrat inexistant).

### Recherche vectorielle, plein texte, référence exacte — 🔴 à mesurer

À faire sur la base locale **ingérée** (`make ingest … INSTANTANE=data/raw/code-assurances-2026-10-20.json`,
qui exige l'accès Azure OpenAI pour les embeddings), avant et après index :

```sql
SET enable_indexscan = off; SET enable_bitmapscan = off;   -- « avant » : scan exact
EXPLAIN ANALYZE <requête de la §1>;
RESET ALL;                                                 -- « après » : HNSW, GIN, B-tree
EXPLAIN ANALYZE <requête de la §1>;
```

Les plans « avant / après » seront collés ici, avec le rappel du HNSW mesuré contre le scan exact.

## 6. Spark SQL (big data) — freMTPL2

*Source : `tools/extraction_bigdata.py` (`make bigdata`, Java 17, groupe uv `bigdata`). Les bornes de filtre
viennent de `fonction-calcul/entrainement/donnees.py` pour la borne haute d'exposition (`EXPOSURE_MAX = 1.0`) et le bonus-malus (`BONUS_MALUS_MIN, BONUS_MALUS_MAX = 50, 230`), les mêmes que celles de la préparation du GLM ; `Exposure > 0` est ajouté par `_FILTRE` dans `tools/extraction_bigdata.py`. Une ligne hors bornes est exclue des agrégats.*

**Chaîne.** Les ARFF freMTPL2freq (OpenML 41214) et freMTPL2sev (41215) sont téléchargés dans le cache
(`FREMTPL2_CACHE`, `/tmp/fremtpl2-cache` par défaut, SHA-256 vérifié), puis convertis en **Parquet** (`freq.parquet`,
`sev.parquet`) et exposés comme vues `freq` et `sev`. La conversion est refaite à chaque exécution
(`mode("overwrite")`) : seul le téléchargement est mis en cache. Parquet est un format **colonnaire** : Spark ne lit
que les colonnes utiles (élagage) et peut pousser les filtres jusqu'à la lecture.

L'instantané `data/raw/fremtpl2-agregats-<date>.json` ne contient que des **agrégats** (aucune ligne de contrat),
au format des autres collectes (manifeste `date`, `environnement`, `perimetre`, `articles`, `sha256`). Mesuré le
29/10/2026 : **25 lignes** (22 régions + 3 tranches de bonus-malus).

### 6.1 Fréquence de sinistres par région (`frequence_par_region`)

*Objectif de collecte* : fréquence de sinistres (sinistres / exposition) par région, base de la tarification.

```sql
SELECT Region, COUNT(*) AS contrats, SUM(Exposure) AS exposition,
       SUM(ClaimNb) AS sinistres, SUM(ClaimNb) / SUM(Exposure) AS frequence
FROM freq
WHERE Exposure > 0 AND Exposure <= 1 AND BonusMalus BETWEEN 50 AND 230
GROUP BY Region
ORDER BY Region
```

- **Sélection** : `Region`, plus quatre agrégats (nombre de contrats, exposition, sinistres, fréquence).
- **Filtres** : exposition dans ]0 ; 1] (une exposition est une fraction d'année), bonus-malus dans [50 ; 230]
  (bornes du coefficient retenues dans `donnees.py`).
- **Condition / regroupement** : `GROUP BY Region` ; pas de jointure.
- **Optimisations**, relevées dans `make bigdata ARGS=--expliquer` :
  - élagage de colonnes : seules 4 colonnes sur les 12 du fichier sont lues ;
  - filtres poussés à la lecture Parquet.

```text
...
PushedFilters: [IsNotNull(Exposure), IsNotNull(BonusMalus), GreaterThan(Exposure,0.0), LessThanOrEqual(Exposure,1.0), GreaterThanOrEqual(BonusMalus,50), LessThanOrEqual(BonusMalus,230)]
ReadSchema: struct<ClaimNb:int,Exposure:double,BonusMalus:int,Region:string>
```

Résumé (hors extrait) : le plan enchaîne `Scan parquet`, `Filter`, `Project`, `HashAggregate` partiel, `Exchange`,
`HashAggregate`, `Sort` ; l'agrégation partielle avant l'`Exchange` (brassage) réduit ce qui circule entre partitions.

### 6.2 Coût moyen par tranche de bonus-malus (`cout_moyen_par_bonus_malus`)

*Objectif de collecte* : coût moyen d'un sinistre selon la tranche de bonus-malus (50-99, 100-149, 150-230),
pour les contrats ayant au moins un sinistre.

```sql
WITH couts AS (
    SELECT IDpol, SUM(ClaimAmount) AS montant, COUNT(*) AS nb
    FROM sev GROUP BY IDpol
)
SELECT /*+ BROADCAST(couts) */
       CASE WHEN freq.BonusMalus < 100 THEN '50-99'
            WHEN freq.BonusMalus < 150 THEN '100-149'
            ELSE '150-230' END AS tranche_bm,
       COUNT(DISTINCT freq.IDpol) AS contrats_sinistres,
       SUM(couts.montant) / SUM(couts.nb) AS cout_moyen
FROM freq
JOIN couts ON freq.IDpol = couts.IDpol
WHERE freq.Exposure > 0 AND freq.Exposure <= 1 AND freq.BonusMalus BETWEEN 50 AND 230
GROUP BY tranche_bm
ORDER BY MIN(freq.BonusMalus)
```

- **Sélection** : tranche (`CASE` sur `BonusMalus`), nombre de contrats sinistrés, coût moyen pondéré
  (montant total / nombre de sinistres, et non moyenne de moyennes).
- **Filtres** : mêmes bornes qu'en 6.1.
- **Jointure** : **interne** (`JOIN`) sur `IDpol`, car seuls les contrats ayant des sinistres (présents dans `sev`)
  ont un coût ; une jointure externe ajouterait des lignes sans montant. `sev` est d'abord agrégé par contrat (CTE
  `couts`) : la jointure porte sur une ligne par contrat, sans multiplier les lignes de `freq`.
- **Optimisations** :
  - jointure par **diffusion** : l'indice `/*+ BROADCAST(couts) */` envoie la petite table `couts` à chaque
    exécuteur, ce qui évite de brasser la grande table `freq` ;
  - élagage de colonnes sur les deux tables, filtres poussés sur `freq` ;
  - agrégation de `sev` avant la jointure (réduit le volume diffusé).

```text
== Physical Plan ==
AdaptiveSparkPlan (21)
+- Project (20)
   +- Sort (19)
      +- Exchange (18)
         +- HashAggregate (17)
            +- Exchange (16)
               +- HashAggregate (15)
                  +- HashAggregate (14)
                     +- Exchange (13)
                        +- HashAggregate (12)
                           +- Project (11)
                              +- BroadcastHashJoin Inner BuildRight (10)
                                 :- Project (3)
                                 :  +- Filter (2)
                                 :     +- Scan parquet  (1)
                                 +- BroadcastExchange (9)
                                    +- HashAggregate (8)
                                       +- Exchange (7)
                                          +- HashAggregate (6)
                                             +- Filter (5)
                                                +- Scan parquet  (4)
...
PushedFilters: [IsNotNull(Exposure), IsNotNull(BonusMalus), GreaterThan(Exposure,0.0), LessThanOrEqual(Exposure,1.0), GreaterThanOrEqual(BonusMalus,50), LessThanOrEqual(BonusMalus,230), IsNotNull(IDpol)]
ReadSchema: struct<IDpol:double,Exposure:double,BonusMalus:int>
...
PushedFilters: [IsNotNull(IDpol)]
ReadSchema: struct<IDpol:int,ClaimAmount:double>
...
(10) BroadcastHashJoin
Left keys [1]: [knownfloatingpointnormalized(normalizenanandzero(IDpol#78))]
Right keys [1]: [knownfloatingpointnormalized(normalizenanandzero(cast(IDpol#90 as double)))]
Join type: Inner
Join condition: None
```

Tri : les tranches sont ordonnées numériquement (`ORDER BY MIN(freq.BonusMalus)`) : `50-99`, `100-149`, `150-230`.

Limites constatées : (a) les bornes d'exposition et de bonus-malus sont filtrées mais non écrêtées, à la différence du GLM
(`donnees.py` écrête) : les agrégats excluent les lignes hors bornes ; (b) `IDpol` est lu en `double` côté `freq`
et en `int` côté `sev` (inférence du schéma CSV) : Spark ajoute un `cast` dans la clé de diffusion, sans effet sur le résultat.
