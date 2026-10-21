# Grille — atelier croisé n°3 « Données et ancrage »

*Livrable L14. Reprise de `grille-atelier-3-donnees-ancrage.pdf` ; champs à remplir pendant l'atelier.
Script de démo : [`docs/demo-atelier-3.md`](../../docs/demo-atelier-3.md).*

**Date** : ______ · **Évaluateur** : ______ · **URL** : `$PROD_URL`

| # | Critère | Preuve montrée | Acquis / partiel / non acquis | Remarques |
|---|---|---|---|---|
| 1 | Sources licites | `docs/donnees/sources.md`, attribution Etalab, vue minimisée, `docs/donnees/rgpd.md` | | |
| 2 | Traçabilité | `citations[]` → `url_source`, `/api/documents/{doc_id}`, `/api/traces/{trace_id}` | | |
| 3 | Refus hors corpus | Question libre → `NOT_FOUND_IN_CORPUS`, `RAG_SEUIL` | | |
| 4 | Pipeline rejouable | `make ingest` en direct → « 0 inséré » ; run de déploiement | | |
| 5 | En production | `$PROD_URL/health` (release, corpus), gateway seule exposée | | |
| — | Journal des retours | Conseil de l'atelier n°2 et sa prise en compte | | |

**Conseil reçu** : ______

**Action décidée** : ______
