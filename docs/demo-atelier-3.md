# Démo — atelier croisé n°3 « Données et ancrage »

*Livrable L13. Tout se fait sur l'URL de **production** : `$PROD_URL` (domaine personnalisé, variable GitHub
`PROD_URL`, tâche G4), par la page Swagger unique de la gateway (`$PROD_URL/`), connecté en Entra (PKCE)
avec le rôle `Gestionnaire`. Questions : `eval/questions-demo.jsonl`.*

## 0. Journal des retours — 2 min

- Conseil reçu à l'atelier n°2 et ce qui a changé depuis : 🔴 à compléter par Acerola.

## 1. Sources licites — 4 min

1. Ouvrir [`docs/donnees/sources.md`](donnees/sources.md) : 3 sources, licence Etalab 2.0, CGU Légifrance.
2. `GET /api/documents/{doc_id}/attribution` sur un article cité : concédant, licence, lien, date d'extraction.
3. `GET /api/contrats/{numero_contrat}` (un contrat du gestionnaire connecté) : la vue ne contient ni nom,
   ni adresse, ni numéro de permis. Puis le numéro d'un contrat d'un autre gestionnaire → **404**, même corps
   qu'un contrat inexistant (BOLA).
4. [`docs/donnees/rgpd.md`](donnees/rgpd.md) : non-applicabilité au corpus, minimisation, registre.

## 2. Traçabilité — 4 min

1. `POST /api/reponses` avec une question couverte du jeu de démo → `citations[]` (article, version, date,
   `url_source`) et `trace_id`.
2. Cliquer sur `url_source` (legifrance.gouv.fr) ; `GET /api/documents/{doc_id}` : versions, hash, date
   d'ingestion.
3. `GET /api/traces/{trace_id}` : le chemin complet sur 3 services (gateway → rag → underwriting-admin),
   sans le texte de la question (sha256 seulement).

## 3. Refus hors corpus — 4 min

1. Une question hors corpus du jeu de démo → `statut = NOT_FOUND_IN_CORPUS`, message propre, aucune citation.
2. Inviter l'évaluateur à poser **sa** question hors sujet ; montrer le verrou qui refuse (span
   `agent.repondre`, attribut `agent.verrou`).
3. Montrer `RAG_SEUIL` dans la configuration de la Container App.

## 4. Pipeline rejouable — 4 min

1. En direct : `make ingest URL=$PROD_URL INSTANTANE=data/raw/code-assurances-2026-10-27.json` → rapport
   « 0 inséré, N inchangés ».
2. Montrer le dernier run de déploiement GitHub Actions (réingestion à chaque déploiement) et
   [`docs/donnees/pipeline.md`](donnees/pipeline.md).

## 5. En production — 4 min

1. `GET $PROD_URL/health` : release `v0.5.0`, version (SHA) ; `/health/rag` (corpus : sha de l'instantané,
   nb de chunks) ; `/health/underwriting`.
2. Seule la gateway est exposée : rag (8001) et underwriting-admin (8002) injoignables de l'extérieur
   (test E2E `test_seule_la_gateway_est_exposee`, job `e2e-staging`).
3. La chaîne : `lint → test → integration → build → staging → e2e-staging + evals → release → production`.

## Questions de secours

- Si l'évaluateur cite un article exact (« Que dit le L211-1 ? ») : la référence exacte passe la porte même
  sous le seuil.
- Si Azure OpenAI est indisponible : `statut = REVUE_HUMAINE`, avec les citations trouvées (mode dégradé).
- Si l'auth Swagger bloque : jeton par `az account get-access-token --resource api://agentinsurflow-rag`.
