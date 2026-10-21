# Recherche — démarche, comparatifs, décisions datées

*Compétence C4 (transverse). Source : spec du sprint 3 (`brief3/2026-10-19-donnees-ancrage-design.md`, §0 et §0 bis)
et registre de suivi de l'implémentation.*

## Démarche

1. **Source fiable et licite** avant tout : l'API Légifrance (Licence Ouverte Etalab 2.0) plutôt que des
   « règles » rédigées à la main (abandonnées).
2. **Citer ou refuser** : chaque réponse s'appuie sur un article, sa version et sa date, sinon elle refuse
   (trois verrous). Le seuil se calibre sur des questions réelles (`make calibrer`).
3. **Une seule base** pour le vectoriel, le plein texte, les dossiers et les traces (PostgreSQL + pgvector).
4. **Tout se rejoue** : instantané versionné, ingestion idempotente (« 0 inséré » au second passage).

## Comparatifs

| Sujet | Options | Retenu | Raison |
|---|---|---|---|
| Index vectoriel | HNSW · IVFFlat · scan exact | **HNSW** | Pas d'entraînement préalable (IVFFlat en exige un sur des données présentes), bon rappel ; le scan exact reste la référence de mesure ([`requetes-sql.md`](requetes-sql.md)) |
| Recherche exacte | Plein texte natif + numéro d'article · extension BM25 | **Plein texte natif + RRF** | Aucune extension à installer ; `ts_rank_cd` n'est **pas** BM25 (pas d'IDF), écart assumé |
| Fusion | Somme pondérée · RRF | **RRF (k = 60)** | Insensible aux échelles de score ; le score RRF ne sert qu'à ordonner |
| Référentiel des traces | OTLP + PostgreSQL · Collector + ClickHouse · App Insights seul | **OTLP + PostgreSQL** | SQL sur les traces sans conteneur de plus ([`traces.md`](traces.md)) |
| Architecture | 1 conteneur applicatif · 3 projets | **3 projets** (gateway, rag, underwriting-admin) | Propriété des données par service, gateway seule exposée |

## Décisions datées (S3-1 → S3-30)

| # | Décision | Date |
|---|---|---|
| S3-1 | Corpus : API Légifrance (bac à sable PISTE), Code des assurances restreint à l'auto ; les « 245 règles » sont abandonnées | 16/10 |
| S3-2 | Périmètre : `L121-*`, `A121-1`, `L211-*`, `R211-*`, `A211-*` ; pas de Code de la route | 16/10 |
| S3-3 | Nouvelle collection `textes_reglementaires` | 16/10 |
| S3-4 | Un seul conteneur applicatif — **remplacée par S3-15** | 16/10 |
| S3-5 | PostgreSQL : conteneur annexe `pgvector` dans la Container App (éphémère) | 16/10 · 19/10 |
| S3-6 | Embeddings `text-embedding-3-small` (1 536 dimensions) | 16/10 |
| S3-7 | Clé pivot `numero_contrat` | 19/10 |
| S3-8 | Colonne `code_postal` ajoutée à `SOUSCRIPTEUR` | 19/10 |
| S3-9 | Quasi-doublons signalés, jamais rejetés | 19/10 |
| S3-10 | Authentification Entra ID ; identités fédérées OIDC pour la CI | 19/10 |
| S3-11 | Recherche exacte : plein texte natif + numéro d'article + RRF (pas un vrai BM25) | 19/10 |
| S3-12 | Mots de passe PostgreSQL : secrets de la Container App, rien dans GitHub | 19/10 |
| S3-13 | Référentiel SQL des traces conforme OpenTelemetry (base `traces`, table `span`) | 19/10 |
| S3-14 | Architecture hexagonale pour le code Python | 19/10 |
| S3-15 | Trois projets dans le monorepo : `rag`, `underwriting-admin`, `gateway` | 19/10 |
| S3-16 | `rag` : corpus, ingestion, recherche hybride, agent à 3 verrous, CLI | 19/10 |
| S3-17 | `underwriting-admin` en ASP.NET Core 10 : dossiers (EF Core, BOLA) et référentiel des traces | 19/10 |
| S3-18 | Gateway YARP, seule entrée publique | 19/10 |
| S3-19 | Une Container App, 4 conteneurs ; `infra/containerapp.yaml` versionné | 19/10 |
| S3-20 | Deux inscriptions d'application ; `rag` → `underwriting-admin` en On-Behalf-Of, identité managée fédérée | 19/10 |
| S3-21 | `/v1/traces` sans jeton depuis la boucle locale sans `X-Forwarded-For` ; sinon rôle `Telemetrie` | 19/10 |
| S3-22 | Pyramide de tests 70 / 20 / 10 | 19/10 |
| S3-23 | Trois branches, une par projet, mergées dans l'ordre | 19/10 |
| S3-24 | API RESTful, page Swagger unique sur la gateway | 19/10 |
| S3-25 | La gateway valide le JWT et le rôle par route ; chaque service revalide | 19/10 |
| S3-26 | IP réelle du client derrière l'envoy (`Proxy__EnvoyDevant`) | 19/10 |
| S3-27 | Limitation de débit native (120/min global, 10/min sur `/api/reponses`) | 19/10 |
| S3-28 | Domaine personnalisé en production, certificat managé | 19/10 |
| S3-29 | La gateway, passage unique du serveur MCP (S4) | 19/10 |
| S3-30 | Déploiement de la gateway avancé (voie B) | 19/10 |

## Décisions et écarts de l'implémentation de `underwriting-admin` (20/10)

| Sujet | Décision | Raison |
|---|---|---|
| Noms des routes | `/api/contrats`, `/api/traces/{trace_id}` (au lieu de `/internal/…`) | Contrat REST S3-24, déjà routé par la gateway |
| Format JSON | snake_case | Les clés que lit `rag` (`numero_contrat`, `tranche_age`…) |
| `rag` → `underwriting-admin` | **Par la gateway** (`UNDERWRITING_URL` = :8000), jeton OBO de l'utilisateur | D22 du dossier (« tout passe par la gateway ») : rôle par route, débit, journal ; remplace l'appel direct sur localhost (C15), le 21/10 à la demande d'Acerola |
| `/v1/traces` en local | `Otlp:SourcesSansJeton` (CIDR) en plus de la boucle locale | Les conteneurs du compose ne partagent pas `localhost` ; Azure garde la boucle seule |
| Swagger | Pas de Swagger UI propre : `/openapi/v1.json` affiché par la gateway | Page Swagger unique (S3-24) |
| `PRIME` | Une prime par contrat (montant, périodicité, date d'effet) | P18, tranché par Acerola |
| Seed | Gestionnaires lus dans `SEED_GESTIONNAIRE_A/B` | Aucun `oid` réel commité |
| Version | Release **v0.5.0** | Décision d'Acerola |
| Pyramide | Porte **informative** en CI (≈ 52 % TU / 46 % TI / 2 % E2E au 20/10) | Décision d'Acerola, en attendant une tâche dédiée aux TU |
