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
make ingest URL=http://localhost:8000 INSTANTANE=data/raw/code-assurances-2026-10-20.json   # ④-⑩ : rejeu
```

En CI, le déploiement réingère l'instantané à chaque déploiement (la base annexe repart vide), avec un jeton
OIDC de la CI.

## Gestion des erreurs

| Cas | Comportement |
|---|---|
| Identifiants PISTE invalides | Message clair, code de sortie non nul |
| 429 / 5xx de Légifrance | 3 nouvelles tentatives à délai croissant, puis échec |
| Article partiel ou invalide | Rejeté avec sa raison, compté dans le rapport, le lot continue |
| Échec d'un lot (base, embeddings) | Transaction annulée pour ce lot, code de sortie non nul |
| Jeton absent ou sans rôle `Ingestion` | 401 / 403 à la gateway, ProblemDetails `NON_AUTHENTIFIE` / `ACCES_REFUSE` |
