# Preuves versionnées

Journaux de chaîne et captures qui prouvent les critères de l'atelier n°2, à verser **après chaque démonstration
ou répétition**. Nommage : `<sujet>-AAAA-MM-JJ.<ext>`.

| Sujet | Produit par | Fichiers attendus |
|---|---|---|
| `livraison` | `make preuve RUN=<id du run du merge> NOM=livraison-AAAA-MM-JJ` | `.log`, `.resume.txt` |
| `evals` | artefact `evals-staging-<sha>` ou `evals-pr-<sha>` (`gh run download <id> -n <nom>`) : manifeste + résultats | `evals-AAAA-MM-JJ.json` |
| `blocage` | `make preuve RUN=<id du run rouge> NOM=blocage-AAAA-MM-JJ` + capture de la PR | `.log`, `.resume.txt`, `-pr.png` |
| `rollback` | `make preuve RUN=<id du run deploy> NOM=rollback-AAAA-MM-JJ` + `/health` avant et après | `.log`, `.resume.txt`, `.md`, `.png` |
| `recette-k` | Recette des K dans l'espace gestionnaire (Acerola pilote, vérifications en lecture seule : état, traces, journaux) | `recette-k-AAAA-MM-JJ-<env>.md` |
| `ingestion` | `make ingest URL=<gateway> INSTANTANE=data/raw/…` (environnement : `APP_ENV` ou `--environnement`) : instantané, lots, insérés, rejets | `ingestion-AAAA-MM-JJ-<env>.json` |

Les journaux GitHub masquent les secrets (`***`). Relire tout de même chaque fichier avant de le committer.
