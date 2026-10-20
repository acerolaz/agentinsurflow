# rag — règles du projet

Corpus Légifrance, ingestion, recherche hybride, agent à 3 verrous. Contrat transverse : [`../CLAUDE.md`](../CLAUDE.md) ;
architecture : `~/.claude/rules/python-hexagonal.md` ; tests : [`../.claude/rules/testing-pyramid.md`](../.claude/rules/testing-pyramid.md).

## Non-négociables

- `domain/` et `application/` sans FastAPI, Pydantic, SQLAlchemy, OpenTelemetry ni SDK (`tests/unit/test_architecture.py`).
- **Citer ou refuser** : porte de pertinence (`RAG_SEUIL` obligatoire), abstention du LLM, au moins une citation ; sinon `NOT_FOUND_IN_CORPUS`.
- Ingestion **idempotente** (rejouer = « 0 inséré ») ; quasi-doublons signalés, jamais rejetés.
- Le texte d'une question n'est **jamais** tracé (sha256 et longueur seulement).
- Dossiers lus chez `underwriting-admin` en On-Behalf-Of ; refus OBO → 503 `DOSSIERS_INDISPONIBLES`, jamais 500.
- Identifiants PISTE dans le `.env` local seulement ; aucun appel réel à Légifrance sans besoin explicite.
