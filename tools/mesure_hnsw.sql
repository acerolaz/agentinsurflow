-- Temps et rappel@10 de HNSW contre le scan exact (critère 2.3), sur vecteurs SYNTHÉTIQUES.
-- Table temporaire : la base n'est pas modifiée.
--   docker exec -i agentinsurflow-postgres-1 psql -U postgres -d vecteurs -q < tools/mesure_hnsw.sql
SELECT setseed(0.42);
\set ON_ERROR_STOP on
CREATE TEMP TABLE centre AS
  SELECT i, array(SELECT random()::real FROM generate_series(1, 1536 + (i - i))) AS v
  FROM generate_series(1, 50) i;
CREATE FUNCTION pg_temp.proche(c real[]) RETURNS vector LANGUAGE sql VOLATILE AS
  $$ SELECT array_agg(x + (random()::real - 0.5) * 0.5)::vector FROM unnest(c) x $$;
CREATE FUNCTION pg_temp.mesurer(volume int) RETURNS TABLE (
  vecteurs int, index_s numeric, exact_ms numeric, hnsw_ms numeric, rappel_pct numeric
) LANGUAGE plpgsql AS $$
DECLARE
  q vector; debut timestamptz; ex bigint[]; ap bigint[]; t_ex float := 0; t_ap float := 0; communs int := 0;
  sql_top text := 'SELECT array_agg(id) FROM (SELECT id FROM item ORDER BY embedding <=> $1 LIMIT 10) t';
  nb_q int := 50; dep timestamptz;
BEGIN
  DROP TABLE IF EXISTS item;
  CREATE TEMP TABLE item (id bigserial PRIMARY KEY, embedding vector(1536) NOT NULL);
  INSERT INTO item (embedding)
    SELECT pg_temp.proche(c.v) FROM generate_series(1, volume) n JOIN centre c ON c.i = 1 + n % 50;
  dep := clock_timestamp();
  CREATE INDEX ON item USING hnsw (embedding vector_cosine_ops);
  index_s := round(extract(epoch FROM clock_timestamp() - dep)::numeric, 1);
  ANALYZE item;
  FOR n IN 1..nb_q LOOP
    q := pg_temp.proche((SELECT c.v FROM centre c WHERE c.i = 1 + n % 50));
    SET LOCAL enable_indexscan = off;
    debut := clock_timestamp();
    EXECUTE sql_top INTO ex USING q;
    t_ex := t_ex + extract(epoch FROM clock_timestamp() - debut);
    SET LOCAL enable_indexscan = on;
    SET LOCAL enable_seqscan = off;
    debut := clock_timestamp();
    EXECUTE sql_top INTO ap USING q;
    t_ap := t_ap + extract(epoch FROM clock_timestamp() - debut);
    SET LOCAL enable_seqscan = on;
    communs := communs + (SELECT count(*) FROM unnest(ex) e WHERE e = ANY (ap));
  END LOOP;
  vecteurs := volume;
  exact_ms := round((t_ex * 1000 / nb_q)::numeric, 2);
  hnsw_ms := round((t_ap * 1000 / nb_q)::numeric, 2);
  rappel_pct := round(communs * 100.0 / (nb_q * 10), 1);
  RETURN NEXT;
END $$;
SELECT * FROM pg_temp.mesurer(127);
SELECT * FROM pg_temp.mesurer(5000);
SELECT * FROM pg_temp.mesurer(20000);
-- Témoin : un ef_search trop petit doit faire chuter le rappel, sinon la mesure ne prouve rien.
SET hnsw.ef_search = 10;
SELECT 'ef_search = 10' AS temoin, * FROM pg_temp.mesurer(20000);
SET hnsw.ef_search = 5;
SELECT 'ef_search = 5' AS temoin, * FROM pg_temp.mesurer(20000);
RESET hnsw.ef_search;
EXPLAIN (COSTS OFF) SELECT id FROM item ORDER BY embedding <=> (SELECT embedding FROM item LIMIT 1) LIMIT 10;
SELECT current_setting('hnsw.ef_search') AS ef_search;
