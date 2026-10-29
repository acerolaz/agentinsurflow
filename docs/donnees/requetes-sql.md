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

À faire sur la base locale **ingérée** (`make agreger` puis `make ingest … JEU=data/aggregated/corpus-2026-10-27.json`,
qui exige l'accès Azure OpenAI pour les embeddings), avant et après index :

```sql
SET enable_indexscan = off; SET enable_bitmapscan = off;   -- « avant » : scan exact
EXPLAIN ANALYZE <requête de la §1>;
RESET ALL;                                                 -- « après » : HNSW, GIN, B-tree
EXPLAIN ANALYZE <requête de la §1>;
```

Les plans « avant / après » seront collés ici, avec le rappel du HNSW mesuré contre le scan exact.
