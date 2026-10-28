# Amendements au dossier de conception (V1.2) — décision D105

**D105 remplace D26 et amende D10, D93 et D100.** Plus aucune exception à D22 : le cluster écrit ses points de reprise LangGraph par la gateway vers underwriting-admin (`/api/points-de-reprise`, rôle `PointsDeReprise`, `azp` du cluster), dans le schéma `points_reprise` de la base annexe, au compte PostgreSQL `points_reprise`. Le cluster n'a plus ni DSN, ni schéma `agent_state`, ni dépendance `langgraph-checkpoint-postgres`. Spec : [`../superpowers/specs/2026-10-28-o8-suppression-d26-design.md`](../superpowers/specs/2026-10-28-o8-suppression-d26-design.md).

Source : `dossier-conception-v1.2.pdf` (hors dépôt). Les textes « actuels » sont recopiés de l'extraction du PDF ; les schémas y sont découpés en fragments (césures, `_` isolés), que je laisse tels quels plutôt que de les reformuler. Marque « à vérifier dans le PDF » : numéro de page non relevé, titre exact de l'encadré à confirmer à la reprise dans le PDF.

| Section | Texte actuel | Texte corrigé |
|---|---|---|
| §4.5.2 ② Mémoire de travail (renvoie à D10, D26) | « C'est l'état EtatDossier, découpé en sections dont chacune n'a qu'un seul écrivain, et sauvegardé par le checkpointer dans agent_state (D10, D26). Le détail est en §4.6. » | « … et sauvegardé par le checkpointer, par la gateway vers underwriting-admin, dans le schéma points_reprise (D10, D105). Le détail est en §4.6. » |
| Tableau des capacités, « Exécution durable (checkpoint) » | « Checkpointer LangGraph dans agent_state (D10, D26) §4.6 » | « Checkpointer LangGraph, stocké par underwriting-admin dans points_reprise via la gateway (D10, D105) §4.6 » |
| §4.6 (tableau des mémoires, « Mémoire de travail ») | « Mémoire de travail · 1 dossier · jusqu'à un outil terminal · agent_state 🔴 P15 durée de conservation » | « … · points_reprise (underwriting-admin, par la gateway) 🔴 P15 durée de conservation ». Les points de reprise restent perdus à chaque déploiement de la base annexe (éphémère). |
| §4.6 (schéma de la fusion) | « dossier · pieces · risque · sources / fiche · prime · validation · pilotage agent_state » | « … pilotage points_reprise » |
| L6 · règle D22 (encadré du schéma) | « ⚠ seule exception (D26) : l'orchestrateur écrit ses checkpoints dans le schéma agent_state » | « L'orchestrateur écrit ses points de reprise par la gateway (D105), dans le schéma points_reprise d'underwriting-admin. » |
| L6 · règle d'architecture | « Règle d'architecture : aucun composant n'en appelle un autre directement — tout appel sortant passe par la gateway (une exception : D26). » | « … tout appel sortant passe par la gateway (aucune exception, D105). » |
| L6 · bloc Base SQL | « 🛡 Garde-fous de sortie + schéma agent_state » | « … + schéma points_reprise (propriété d'underwriting-admin) » |
| L6.7 · tableau « Schéma agent_state » | « Schéma agent_state — checkpoints LangGraph de l'EtatDossier (§4.6) : vue minimisée, risque, sources, fiche, validation, prime, pilotage — aucune donnée identifiante. Seule exception à D22 (D26) : utilisateur base sans aucun droit sur les tables métier » | « Schéma points_reprise — points de reprise LangGraph de l'EtatDossier (§4.6), stockage opaque : tables migrées par EF Core, compte points_reprise sans droit sur les tables métier, lu et écrit seulement par underwriting-admin. Aucune exception à D22 : le cluster y accède par la gateway (D105). » |
| Q8 | « Q8 « Tout passe par la gateway, mais l'agent écrit en base ? » — Une seule exception documentée : ses checkpoints, dans un schéma sans droit métier — L6.7 · D26 » | « Q8 « Tout passe par la gateway, et l'agent écrit en base ? » — Non : plus d'exception. Ses points de reprise passent par la gateway vers underwriting-admin, qui seul accède à la base — L6.7 · D105 » |
| D93 (Mémoire court terme) | « Mémoire court terme : checkpointer PostgresSaver (agent_state), thread_id = numero_contrat » | « Mémoire court terme : checkpointer LangGraph à adaptateur HTTP (`CheckpointerHttp`), points de reprise dans points_reprise via la gateway, thread_id = numero_contrat (D105) » |
| D100 (fin) | « … ; le checkpointer reste la mémoire court terme technique » | inchangé, plus : « … le checkpointer reste la mémoire court terme technique, désormais écrite par underwriting-admin (D105) » |
| Tableau des décisions (colonne « amende ») | « amende D64, D26, D93 » (et « précise D26 ») | Ajouter la ligne : « D105 — Points de reprise par la gateway vers underwriting-admin (schéma points_reprise) ; remplace D26, amende D10, D93, D100 ». |
| §7.4 Capacités, « Mémoire court terme » | « Checkpointer PostgresSaver, thread_id = numero_contrat — D93 » | « Checkpointer LangGraph via la gateway (D105), thread_id = numero_contrat — D93 » |
| Addendum du 22/10 | « D22 n'a toujours qu'une exception (D26). » | « D22 n'a plus d'exception : D105 remplace D26 (points de reprise par la gateway vers underwriting-admin). » |
| Addendum et §6 (mentions annexes) | « … le checkpointer garde son exception D26 pour le seul schéma technique agent_state » ; « aucun accès direct à la base (sauf le checkpointer, exception D26) » | Retirer l'exception : « aucun accès direct à la base ». À vérifier dans le PDF : fin de la première phrase, coupée à la page. |
| R16 (risques) | « Checkpoint et base SQL divergent — La base fait foi ; checkpoint reconstruit ; K11 » | inchangé (la base SQL fait toujours foi) ; K11 est à rejouer en staging après la fusion. |

## Écarts connus avec le texte du plan

- Le PDF n'a pas de section intitulée exactement « Tableau Schéma agent_state » : c'est une ligne du tableau « Modèle de données V1 — deux bases » (§6.7, fragments « Schéma agent_state check points LangGraph … »).
- Nom du compte et du secret : `points_reprise`, `pg-points-reprise-password`, variable `PG_POINTS_REPRISE_PASSWORD`.

## Mesures (Task 5)

Relevées sur le **faux underwriting-admin** pendant `test_reprise_apres_interrupt_par_http`, avec un **état de test réduit** : ni point réel PostgreSQL, ni réseau. À confirmer par K11 en staging (mesure réelle, p95 ajouté : [`eval/preuves/recette-k11-AAAA-MM-JJ-staging.md`](../../eval/preuves/recette-k11-AAAA-MM-JJ-staging.md)).

| Scénario | GET | PUT de point | PUT d'écritures | PUT maximal |
|---|---|---|---|---|
| Évaluation | 4 | 8 | 8 | 3 564 o |
| Reprise | 3 | 2 | 3 | 3 996 o |

Aucun `DELETE`, aucune liste. Taille maximale d'environ 4 Ko, loin sous la limite Kestrel par défaut (30 Mo) : un appel par point suffit, sans lot ni cache.
