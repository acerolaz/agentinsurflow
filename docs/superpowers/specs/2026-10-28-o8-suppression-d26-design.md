# O8 — Supprimer D26 : les points de reprise de la Saga passent par la gateway

*Spec de la session S4 du sprint 5 — 28/10/2026. Découpage : [`2026-10-28-sprint5-sessions.md`](2026-10-28-sprint5-sessions.md). Indépendante des autres sessions. Issue #154.*

## 1. Intention

Rendre la règle **D22** (topologie en étoile : tout appel sortant passe par la gateway ; chaque stockage n'est accessible que par son service propriétaire) **sans exception**. Aujourd'hui, l'exception **D26** laisse la Saga écrire ses points de reprise LangGraph directement dans PostgreSQL (schéma `agent_state`, `AsyncPostgresSaver`, secret `checkpoint-dsn`). Après S4, le cluster n'a plus aucun accès réseau ni identifiant vers la base : il passe par la gateway vers **underwriting-admin**, seul propriétaire de la base. C'est le fix d'architecture demandé par Acerola (D-V16) ; preuve C21 : PR, K11 rejoué, dossier mis à jour.

## 2. Objectifs

1. **Côté cluster** : un adapter de sortie `CheckpointerHttp` qui implémente `BaseCheckpointSaver` de LangGraph (version figée `langgraph-checkpoint` 4.3.0, méthodes asynchrones utilisées par le graphe : lecture d'un point, liste, écriture d'un point, écriture des écritures en attente, suppression d'un fil). Il appelle la gateway avec le **jeton d'application du cluster**, comme le fait déjà l'écriture de la section d'état (`PUT /api/contrats/{numero_contrat}/etat`).
2. **Côté gateway** : de nouvelles routes YARP vers underwriting-admin, réservées au cluster (rôle dédié et `azp` du cluster, sur le modèle des routes d'écriture existantes).
3. **Côté underwriting-admin** :
   - des API de lecture et d'écriture des points de reprise ;
   - des tables migrées par EF Core (remplacent les tables d'`AsyncPostgresSaver` dans `agent_state`) ;
   - un rôle d'application dédié (*mon choix de nom* : `PointsDeReprise`), accordé à la seule inscription du cluster.
4. **Retraits** :
   - `INSURFLOW_CHECKPOINT_DSN`, le secret `checkpoint-dsn`, la vérification du secret dans `deploy.yml`, la dépendance `langgraph-checkpoint-postgres` ;
   - le compte et le schéma `agent_state` dans `infra/postgres/init.sh` et `infra/postgres-annexe.sh` ;
   - l'image PostgreSQL annexe, si son tag ne change qu'à cause d'`agent_state` (à vérifier).
5. **K11 rejoué en staging** : `make recette ACTION=redemarrer`, le dossier en pause reprend à l'étape suivante. Preuve dans `eval/preuves/`.
6. **Latence mesurée** : temps ajouté par les appels de points de reprise, par évaluation, comparé à la garde globale de 25 s ; consigné dans la preuve. Ces appels apparaissent dans App Insights comme des dépendances (si S1 est fusionnée) ; sinon dans le référentiel SQL des traces.
7. **Dossier de conception** : la liste des modifications à reporter dans `dossier-conception-v1.2.pdf`, sous la forme section · texte actuel · texte corrigé (`docs/dossier/amendements-d105.md`, *mon choix d'emplacement*). Nouvelle décision **D105** qui remplace D26 et amende D10, D93 et D100. Sections : §4.6 (exécution durable), L6 (règle D22 et schéma), L6.7, tableau « Schéma agent_state », Q8, et l'addendum (« D22 n'a toujours qu'une exception »).

## 3. Non-objectifs

- Rendre les points de reprise **durables entre deux déploiements** : la base annexe reste éphémère, comme aujourd'hui (`docs/rollback.md`).
- Changer le comportement de pause, de reprise ou de la porte HITL (`interrupt()`, K4) : le contrat fonctionnel ne bouge pas.
- Exposer les points de reprise au gestionnaire ou à l'espace : API **internes au cluster**.

## 4. Anti-objectifs

- Une évaluation qui dépasse le budget de 25 s à cause des allers-retours HTTP.
- Un point de reprise lisible par un autre appelant que le cluster (gestionnaire, MCP, rag) : refus 403, testé.
- Le contenu d'un point de reprise (état du graphe : vue du dossier, rapports) dans une trace ou un journal. Le corps HTTP n'est jamais tracé ; les spans portent le gabarit de route, sans `numero_contrat`.
- Une logique LangGraph réimplémentée dans underwriting-admin : il **stocke et rend**, il n'interprète pas.
- Un repli silencieux vers `MemorySaver` en Azure si la gateway est injoignable. En Azure, l'échec doit être visible (erreur, puis alerte via S2) ; `MemorySaver` reste réservé aux tests.

## 5. Contraintes

- Hexagonal côté cluster : le port existe implicitement (`checkpointer()` dans `infrastructure/langgraph/checkpoint.py`) ; l'adapter HTTP vit dans `infrastructure/`, à côté.
- Clean Architecture côté underwriting-admin (.NET 10), sans couche Application artificielle : les points de reprise sont un stockage opaque (Api → Infrastructure).
- Aucune montée de version de LangGraph ; la seule dépendance retirée est `langgraph-checkpoint-postgres` (et, si plus utilisés ailleurs, `psycopg` et `psycopg_pool` côté cluster).
- Écritures Entra (nouveau rôle d'application, son attribution au cluster) : dans `infra/entra.sh`, **lancées à la main** par Acerola.
- `thread_id = numero_contrat` (existant, `graphe.py`).
- Gel des fusions du 29/10 au matin à la fin de la démo du 30/10.

## 6. Décisions

| Décision | Par |
|---|---|
| Supprimer D26 : points de reprise par la gateway vers underwriting-admin ; D22 sans exception | Acerola (D-V16) |
| Rôle et `azp` dédiés au cluster ; nouvelles API de lecture et d'écriture ; tables migrées depuis `agent_state` | Acerola (O8) |
| **Stockage opaque** : underwriting-admin conserve les champs sérialisés par le sérialiseur de LangGraph (octets, encodés en base64 dans le JSON HTTP), indexés par (`thread_id`, `checkpoint_ns`, `checkpoint_id`) et, pour les écritures en attente, par (`task_id`, `idx`). Aucun schéma métier de l'état du graphe | *mon choix* |
| **Pas de cache** côté cluster | *mon choix* (seul un aller-retour mesuré trop lent le justifierait) |
| Tests du cluster : la suite de conformité du saver (lecture après écriture, liste ordonnée, écritures en attente, reprise après `interrupt()`) jouée contre un **faux** underwriting-admin (fake HTTP), plus un test d'intégration contre le vrai underwriting-admin du compose | *mon choix* |

## 7. Preuves de fin de session

1. Les TU et TI des trois services sont verts ; l'ancien `test_checkpoint_postgres.py` est remplacé.
2. `make up` : une évaluation avec une pause puis une reprise fonctionne en local.
3. Staging : K11 rejoué (`make recette ACTION=redemarrer`), consigné dans `eval/preuves/recette-k11-<date>-staging.md`, avec la latence ajoutée.
4. Le cluster ne contient plus aucune référence à `INSURFLOW_CHECKPOINT_DSN`, `checkpoint-dsn` ou `agent_state`, ni son YAML, ni `deploy.yml` (vérifié par recherche dans le dépôt).
5. `docs/dossier/amendements-d105.md` prêt à reporter ; README, `docs/rollback.md` et `docs/contrat-personnel.md` (K11) à jour.

## 7 bis. Précisions issues de la relecture (28/10)

- **ORM** : underwriting-admin utilise déjà EF Core, avec des migrations par contexte (`Infrastructure/Dossiers/Migrations`, `Infrastructure/Traces/Migrations`). Les points de reprise suivent le même modèle (*mon choix* : un contexte dédié, à l'image de `Traces`), dans la base annexe qu'underwriting-admin possède déjà.
- **Données** : la base annexe est éphémère, donc **aucune copie de données**. On crée les nouvelles tables, puis on retire le schéma et le compte `agent_state`.
- **Latence** : aucun seuil n'est inventé. La porte des evals existante (p95 ≤ 30 s) doit rester verte. Le surcoût par évaluation est **mesuré et consigné** (nombre d'allers-retours, p95 ajouté) dans la preuve K11. On ne fait de lot d'écritures ou de cache que si la porte casse.
- **Ordre de déploiement** : `deploy.yml` déploie dans l'ordre base, underwriting-admin, MCP, cluster, gateway, rag. Le nouveau cluster peut donc démarrer avant que la gateway ait la nouvelle route. Les évaluations seront brièvement indisponibles pendant le déploiement, ce qui est déjà accepté aujourd'hui (`docs/rollback.md`) ; le constructeur vérifie si avancer la gateway avant le cluster est possible et sans risque. Le rôle Entra est créé et attribué **avant la fusion** : cette étape figure dans la liste de contrôle de la PR.
- **Taille des points de reprise** : le constructeur mesure en local la taille d'un point de reprise réel et vérifie les limites de corps de Kestrel et de YARP, avant de choisir entre un appel par point et un appel par lot.

## 8. Laissé au constructeur

- La forme exacte des routes (*suggestion* : `/api/points-de-reprise/{thread_id}/…`), les codes HTTP et la pagination de la liste.
- Le mode de suppression d'un fil, et à quel moment.
- La gestion de deux révisions du cluster qui écrivent en même temps pendant un déploiement (R17) : dernier écrit gagnant ou conflit 409, à justifier.
