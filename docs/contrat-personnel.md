# Contrat personnel — état au 23/10 (Sprint 4, cluster d'agents 7a)

*Ce qui a été promis au Sprint 1 (critères K1 à K11 du dossier) face à ce qui est en production ou en code livré, critère par critère. Statuts : **tenu**, **en cours** (le travail est prévu, la preuve n'est pas encore complète), **avenant** (le critère change, avec l'accord d'Acerola). Un inconnu est marqué `🔴 À CONFIRMER`, jamais inventé.*

*Sources : `docs/superpowers/specs/2026-10-23-agentic-cluster-7a-design.md` (avenants A1 à A5, § 5, § 7, § 8), `agentic-cluster/README.md`, journal des rulings R1 à R22 de l'exécution (`.superpowers/sdd/2026-10-23-agentic-cluster-7a/progress.md`), mesures de `task-13-report.md`. Chaque preuve est un fichier de test, une commande ou une route que l'évaluateur peut relancer.*

> **Périmètre honnête.** Le code du cluster est livré sur `feat/cluster` (PR en brouillon). Le **déploiement Azure** du cluster (Container Apps, inscriptions Entra, base `agent_state`) est écrit dans `infra/` mais lancé par Acerola : `🔴 À CONFIRMER` à la date de la démo. Les parcours E2E avec évaluation (OBO) se lancent **depuis un poste** (`az login`), pas en CI.

## 1. K1 à K11

| # | Critère (titre du dossier) | Statut | Preuve | Écart / avenant |
|---|---|---|---|---|
| K1 | Décision homogène et justifiée : 3 dossiers de référence (acceptable, refus, limite) | **en cours** | Tests unitaires : `agentic-cluster/tests/unit/test_agents.py::test_sans_llm_meme_proposition` (cas `acceptable`, `refus`, `hors_bareme`) ; `tests/integration/test_api_cluster.py::test_evaluation_en_analyse_puis_rejeu_409_puis_revue_accepte` (fiche `ACCEPTE`, prime `600.00`, 4 agents enchaînés) ; `tests/unit/test_agents.py::test_hors_bareme_risque_limite_section_remplie_repli` | Le barème (`bareme-2026.10-v1`) n'a pas de classe « limite » : un dossier hors barème (`DONNEE_HORS_BAREME`) devient `limite` (R2, R7, ★ du plan). **Les 3 dossiers de référence ne sont pas encore joués sur l'environnement déployé** : à faire en staging (`🔴 À CONFIRMER` : choix des 3 contrats de démo) |
| K2 | Minimisation RGPD : aucune donnée identifiante dans un appel LLM ni dans une trace (Langfuse supprimé, D103 : contrôle par requête sur les traces) | **en cours** (code tenu, preuve par requête reportée à #54) | `tests/unit/test_agents.py::test_observations_seulement_dans_la_vue_du_redacteur_et_balisees` ; `tests/integration/test_api_cluster.py::test_le_jeton_n_est_ecrit_dans_aucun_point_de_reprise`, `::test_observations_jamais_dans_un_point_de_reprise_mais_recues_par_le_redacteur`, `::test_audit_agent_un_enregistrement_par_agent_sans_donnee_personnelle` (empreinte SHA-256 des observations évaluées, jamais le texte) ; `::test_motif_avec_donnee_personnelle_422_sans_reprendre_la_revue` ; `tests/unit/test_telemetrie_cluster.py::test_span_invoke_agent_porte_l_agent_le_mode_et_la_cause_seulement` ; `tests/unit/test_pii.py` ; MCP : `serveur-mcp/tests/integration/test_traces.py` | Aucune observation, aucun jeton, aucun nom dans les traces, les points de reprise ni `audit.agent` (empreintes SHA-256 seulement, `enable_content_recording=False`). La preuve « requête sur les traces » en ligne (`GET /api/traces/{trace_id}` puis requête SQL, ou KQL) dépend du déploiement (R19) et d'Application Insights (#54, R14) : `🔴 à brancher (#54)` pour la version KQL |
| K3 | RBAC par appelant + portefeuille (OWASP API1, BOLA) : jeton de l'Agent Actuaire, du Rédacteur, puis du gestionnaire B | **tenu** | Matrice `azp` × outil (MCP) : `serveur-mcp/tests/integration/test_protocole.py::test_redacteur_appelle_update_statut_dossier_UNAUTHORIZED_TOOL_sans_appel_backend`, `::test_actuaire_appelle_enregistrer_etat_UNAUTHORIZED_TOOL_sans_appel_backend` ; `test_outils_calcul.py::test_outil_non_autorise` (Rédacteur → `calculer_prime`) et `::test_actuaire_ne_voit_que_calculer_prime` ; `test_outils_ecriture.py::test_redacteur_ne_peut_pas_ecrire`. Cluster : `tests/unit/test_agents.py::test_chaque_agent_appelle_son_outil_avec_son_azp_et_le_jeton`. Gestionnaire B : `underwriting-admin/tests/.../ObservationsTests.cs::Autre_gestionnaire_404_et_valeur_inchangee`, `EtatTests.cs::Autre_gestionnaire_404_et_aucune_ligne`, `e2e/test_parcours.py::test_contrat_d_un_autre_gestionnaire_404`. Gateway : `gateway/tests/.../ClusterTests.cs` (audience, rôle, 403 `ACCES_REFUSE`) | Les jetons d'agent sont obtenus **par le cluster** (OBO en deux sauts) : un évaluateur ne peut pas les réclamer lui-même depuis un poste. La preuve des refus par agent est donc dans les tests ; le gestionnaire B se montre en direct (404) |
| K4 | Validation humaine : base consultée avant et après validation | **tenu** | `tests/integration/test_api_cluster.py::test_evaluation_en_analyse_puis_rejeu_409_puis_revue_accepte` (statuts écrits : `EN_ANALYSE` puis `ACCEPTE` ; rejeu `409 EVALUATION_EN_ATTENTE` ; `/revue` sans attente `409 AUCUNE_REVUE_EN_ATTENTE`) ; `::test_revue_non_perdue_si_l_enregistrement_echoue_puis_rejoue` ; `tests/unit/test_evaluation.py::test_dossier_acceptable_brouillon_puis_en_analyse_jamais_accepte`. Démo : `GET /api/contrats/{n}` avant et après `POST …/revue` (voir `docs/demo-atelier-4.md`) | L'agent n'écrit jamais `ACCEPTE` (A4) ; le motif de la revue est dans la section `validation` de l'état, pas dans `DECISION` (R13) |
| K5 | Résilience : LLM coupé par variable d'environnement : « Service temporairement indisponible » < 30 s, REVUE_HUMAINE + score | **en cours** | `INSURFLOW_LLM_ACTIF=false` (`agentic-cluster/agentinsurflow_cluster/infrastructure/llm/modele.py` : sans modèle, `rediger` rend `None`) ; `tests/unit/test_agents.py::test_lent_none_repli_avec_reference` (cause `llm_ko`, repli de référence, Rédacteur en section vide) ; `::test_sans_llm_meme_proposition` ; `tests/integration/test_api_cluster.py::test_k5_llm_inactif_200_revue_humaine_score_et_message_indisponible` (API complète, LLM coupé : `200`, `REVUE_HUMAINE`, `score` du barème, message exact, < 30 s) ; `::test_k5_pii_en_sortie_n_est_pas_une_panne_du_llm` ; `::test_budget_depasse_dans_un_agent_revue_humaine_cause_duree` et `::test_budget_depasse_avant_tout_etat_503_delai_depasse` (garde 25 s + réserve 2 s, `INSURFLOW_BUDGET_S`, `INSURFLOW_RESERVE_S`) | **Code conforme au dossier.** LLM coupé (cause `llm_ko`), le Rédacteur n'a pas de sortie ⇒ `REVUE_HUMAINE`, `score` du barème dans la réponse et dans la fiche provisoire du brouillon (R13), message **« Service temporairement indisponible »** (`MESSAGE_INDISPONIBLE`). Les autres revues humaines gardent le message neutre **« Ce dossier nécessite une revue humaine. »**, y compris une détection PII en sortie du LLM (cause distincte `garde_fou:pii`, qui n'est pas une panne). Délai < 30 s prouvé avec des ports factices ; non mesuré en conditions réelles : `🔴 À MESURER` en staging |
| K6 | Accessibilité RGAA 11.1 / WCAG 2.1.1 : parcours complet sans souris | **avenant** | Aucune. Le sprint 4 (7a) n'a pas d'interface : la démo passe par la page Swagger de la gateway | Pas d'UI en 7a (#38). Le critère est reporté avec l'UI : coût si faux, ci-dessous (§ 2) |
| K7 | Prime déterministe, en brouillon : évaluation rejouée avec et sans LLM de l'Actuaire | **tenu** | `tests/unit/test_agents.py::test_k7_actuaire_avec_ou_sans_llm_meme_prime_meme_fiche` ; `::test_actuaire_menteur_montant_ga1_repli_reference` ; `::test_actuaire_menteur_version_ga2_repli_reference` ; `::test_actuaire_valide_reprend_les_montants_exacts_de_la_reference` ; `serveur-mcp/tests/integration/test_outils_calcul.py::test_actuaire_calcule_la_prime` | La prime vient du calcul (Function) ; le LLM ne rédige que l'explication. Réserve connue : l'indépendance Rédacteur/Actuaire est faiblement prouvée (reportée) |
| K8 | Relances bornées et fin de parcours (`SANS_SUITE`) | **en cours** | Aucune en 7a | Livrée en **7b** (colonnes de relance sur `CONTRAT` : point ouvert P23) |
| K9 | Saga auditable et observable (Application Insights : Application Map, Transaction Diagnostics, Live Metrics, KQL sur `audit.agent`) | **en cours** | `tests/integration/test_api_cluster.py::test_audit_agent_un_enregistrement_par_agent_sans_donnee_personnelle` ; `tests/unit/test_telemetrie_cluster.py` ; `tests/unit/test_export_otlp_cluster.py` (export OTLP par la gateway, jeton d'application) | Le cluster exporte en **OTLP** vers le référentiel des traces d'underwriting-admin, comme le serveur MCP (R14, R19). **Application Insights est reporté à #54** (jalon 15/11) : Application Map, Live Metrics et KQL ne sont pas démontrables aujourd'hui |
| K10 | L'outil de relance reste borné (saboteur ⇒ refus tracés) | **en cours** | Aucune en 7a | Dépend de l'outil de relance, livré en **7b**. Les modes saboteurs sont déjà couverts pour les 4 agents (menteur, fuite, injecte, intrus, lent, casse : `tests/unit/test_agents.py`) |
| K11 | Mémoire long terme du dossier (redémarrage du cluster puis reprise ; SQL sur `RAPPORT_AGENT`) | **en cours** | Tables `ETAT`, `SECTION_ETAT`, `RAPPORT_AGENT` (migration `MemoireDossier`, `underwriting-admin/tests/.../EtatTests.cs::Deux_put_identiques_une_ligne_d_etat_et_un_seul_rapport`) ; `AsyncPostgresSaver` (`agentinsurflow_cluster/infrastructure/langgraph/checkpoint.py`, schéma `agent_state`) | La **démonstration de reprise après redémarrage** n'est pas faite : à jouer en staging. Sans `INSURFLOW_CHECKPOINT_DSN`, les points de reprise sont en mémoire (reprise impossible : `409`). Attention : la base annexe est **éphémère** (`docs/rollback.md`) : une nouvelle révision de la base repart vide ; la reprise vaut donc pour un redémarrage du cluster, pas pour un déploiement de la base |

**Bilan** : 3 tenus (K3, K4, K7), 7 en cours (K1, K2, K5, K8, K9, K10, K11), 1 avenant (K6).

### Écarts ★ du plan portés au contrat

- **La gateway relaie le jeton (R18).** Elle n'échange pas le jeton du gestionnaire pour le cluster, comme pour `/mcp`. « Seule la gateway appelle le cluster » (D105) est garanti par l'**entrée interne** de la Container App et par la **revalidation** du jeton par le cluster (signature, émetteur, audience, rôle `Gestionnaire`), et non par `azp = gateway`. Le cluster échange ensuite ce jeton pour chaque agent (OBO), d'où un `azp` propre à chaque agent côté MCP.
- **Pièces incomplètes ⇒ revue humaine en 7a** (R2) : l'Analyste ne tourne que si les pièces sont complètes, sauf pour un dossier bloqué à l'entrée (le score est exigé par la spec § 3.3).
- **`DONNEE_HORS_BAREME` ⇒ classe `limite`** (R2, R7) : un dossier que le barème ne sait pas noter va en revue humaine, sans effet sur la décision, qui reste humaine.
- **Limite de réplique (R17).** Le verrou par dossier est un `asyncio.Lock` : valable pour **une réplique** (`maxReplicas: 1`). Pendant un déploiement, l'ancienne et la nouvelle révision peuvent coexister brièvement : le verrou n'est pas garanti dans cette fenêtre.
- **E2E avec évaluation depuis un poste.** Le cluster échange le jeton d'un gestionnaire (OBO) : un jeton d'application (CI) ne passe pas. `e2e/test_cluster.py::test_dossier_complet_en_analyse_puis_revue` et `::test_observations_hostiles_revue_humaine_et_message_neutre` sont **sautés en CI** et se lancent avec `az login`. La CI vérifie la santé, le 401 sans jeton et l'inaccessibilité de l'URL interne.
- **Tests `lent` hors CI.** Les tests d'intégration marqués `lent` (modèles LLM Guard réels : `tests/integration/test_llm_guard.py`, `test_jeu_garde_fous.py`, `make garde-fous`) ne tournent **pas** en CI (≈ 2,5 Go de modèles) : ils se lancent à la main (`uv run pytest agentic-cluster/tests -m lent`) ; la CI ne rejoue que les garde-fous simulés.
- **Taux de faux positifs mesuré** : voir § 3.

## 2. Avenants

Chaque ligne indique le **coût si faux** : ce que coûte la décision si elle se révèle mauvaise.

### Avenants A1 à A5 (décidés par Acerola le 23/10, spec § 3.1)

| # | Avenant | Coût si faux |
|---|---|---|
| A1 | Champ libre **observations du gestionnaire** sur `CONTRAT` (texte borné à 2000 caractères), transmis au **Rédacteur seul**, balisé `<donnees_non_fiables>`, après le garde-fou d'entrée. Route `PUT /api/contrats/{numero_contrat}/observations`. Amende P12 et D39 | Une vue du Rédacteur plus large que prévu (surface d'injection) : retirer le champ ou le passer par un agent dédié |
| A2 | **LLM Guard** (Protect AI) est le SDK des garde-fous d'entrée et de sortie, dans les middleware de D96. **Précisé le 23/10** : voir « injection » ci-dessous | Dépendance lourde (≈ 2,5 Go de modèles, démarrage à froid) : à remplacer par des règles pures si elle gêne |
| A3 | Garde-fous d'entrée **dans le cluster**, au chargement du dossier (`charger`, 0 LLM), avant tout appel LLM. `underwriting-admin` accepte la saisie telle quelle | Une saisie hostile est stockée en base (jamais exécutée) : filtrer aussi à l'écriture |
| A4 | Action sensible = toute décision qui requiert le gestionnaire : le brouillon attend `POST …/revue` derrière `interrupt()`. Pas de confirmation supplémentaire en 7a | Une validation de plus à ajouter si le dossier l'exige |
| A5 | Refus = message **neutre** pour l'appelant ; cause détaillée dans `audit.agent`, sans PII | Un évaluateur qui veut comprendre un refus doit passer par les traces, pas par la réponse |

### Décisions d'Acerola le 23/10 (exécution)

| Décision | Effet | Coût si faux |
|---|---|---|
| **Forcer nos versions** : `[tool.uv] override-dependencies` sur `cryptography==50.0.2` et `regex==2026.9.29` (versions actuelles du lock) | Aucune rétrogradation ; compatibilité avec presidio vérifiée par le test d'intégration de T9 | Une incompatibilité avec une dépendance d'LLM Guard apparaîtrait à l'exécution, pas à l'installation |
| **torch CPU** depuis l'index PyTorch (même version) | Image réduite de 24,9 Go ; ≈ 9 Go pour la CI | Inférence plus lente que sur GPU (sans objet : pas de GPU en Container Apps) |
| **Injection = règles FR/EN déterministes (bloquantes) + modèle LLM Guard en signal seulement** (avenant à A2) | Les règles donnent la revue humaine et le refus poli ; le score du modèle est journalisé (`signal_injection`), sans bloquer | Des injections subtiles passent l'entrée (sans effet sur la décision : § 3) |

### Rulings qui changent ce qui était promis

| Ruling | Ce qui change | Coût si faux |
|---|---|---|
| R1 | `proposer` convertit la prime annuelle en `PrimeBrouillon` (`periodicite = "annuelle"`) : la forme de l'outil MCP existant fait foi | La prime mensuelle n'est pas stockée : colonne à ajouter |
| R2 | Dossier bloqué à l'entrée : Pièces puis Analyste tournent en repli (score) puis revue humaine, précondition de l'Analyste levée dans ce seul cas | Un hostile sans relevé obtient un score sur faits incomplets (sans conséquence sur la décision) |
| R6 | GF6 vérifie seulement que le contrat type vient de la collection `notices_produits` ; la correspondance à la formule (P13) n'est pas vérifiée | Un contrat type d'une autre formule passe GF6 (le gestionnaire le voit à la revue) |
| R7 | Rapport à section vide + cause ⇒ cause de l'état ; section remplie ⇒ repli, cause dans le rapport seulement | Un échec d'outil de l'Analyste mènerait en revue au lieu d'une erreur 5xx (résultat prudent) |
| R13 | Le motif de `/revue` est conservé dans la section `validation` de l'état, pas dans `DECISION` ; un `REVUE_HUMAINE` sans fiche crée un brouillon provisoire avec le score | Le motif n'est pas dans la table `DECISION` : audit RGPD art. 22 par `ETAT` / `SECTION_ETAT` |
| R14 | Observabilité du cluster : OTLP + `audit.agent` en journal structuré ; **Application Insights reporté à #54** (15/11) | K9 demandera le branchement `azure-monitor` |
| R15 | `AsyncPostgresSaver` si `INSURFLOW_CHECKPOINT_DSN`, sinon `MemorySaver` avec avertissement | En local, une reprise après redémarrage du conteneur échoue (`409`) |
| R16 | Observations transportées par le contexte d'exécution (mémoire), jamais dans l'état ni dans les points de reprise | Le Rédacteur ne les reçoit plus après une reprise (sans objet en 7a : il tourne avant l'`interrupt`) |
| R17 | Verrou `asyncio` par dossier, valable pour une réplique ; `409 DOSSIER_DECIDE` si déjà décidé | En multi-réplique : verrou PostgreSQL à ajouter |
| R18 | La gateway **relaie** le jeton ; D105 par entrée interne + revalidation, pas par `azp = gateway` | Ajouter un échange OBO dans la gateway (YARP) |
| R19 | Export OTLP du cluster branché en Azure (gateway `/v1/traces`, jeton d'application, rôle `Telemetrie`) ; les preuves K2 en dépendent | Une attribution de rôle Entra de plus |
| R21, R22 | Défense en deux couches, **précision d'abord** : une règle exige une adresse aux consignes de l'assistant ou une décision imposée avec marqueur d'injection | Moins d'injections refusées visiblement à l'entrée (la neutralisation couvre le reste) |
| K6 (avenant) | Pas d'interface en 7a (#38) | Le critère d'accessibilité reste non évalué jusqu'à l'UI |

## 3. Garde-fous : mesures

### Les quatre taux (finals, `task-13-report.md`, sections « Révision » et « Fix round 2 »)

| Jeu | Taille | Résultat |
|---|---|---|
| Hostiles (`eval/garde-fous/hostiles.jsonl`) détectés à l'entrée | 38 | **84,2 %** (32/38) ; neutralisés seulement : H02, H03, H06, H10, H14, H36 |
| Réserve hostile (`hostiles_reserve.jsonl`, écrite **après** les règles, jamais retouchée) | 10 | **10 %** (1/10, R08) |
| Faux positifs, légitimes (`legitimes.jsonl`) | 34 | **0 %** |
| Faux positifs, réserve légitime (`legitimes_reserve.jsonl`, dont 4 phrases vues après coup) | 33 | **0 %** ; soit **0/67** sur les deux jeux |

À cela s'ajoutent **8 injections classiques verrouillées par un test unitaire** (`tests/unit/test_injection.py::test_injections_classiques_restent_detectees`), listées dans `docs/demo-atelier-4.md`.

Lecture honnête : la précision a été obtenue au détriment du rappel. Les règles, écrites sur le jeu, généralisent mal (10 % sur la réserve neuve). Le plafond `PLAFOND_FAUX_POSITIFS=0.00` est un plafond mesuré sur 67 lignes, sans marge. Le modèle d'injection de LLM Guard est saturé (score 0 ou 1) et juge une part importante du français légitime comme injection : il n'est donc qu'un **signal journalisé**.

### Défense en deux couches

1. **Les règles d'entrée** (`domain/injection.py`, 10 motifs documentés, stdlib) : refus **visible** des injections franches. Dossier bloqué ⇒ `REVUE_HUMAINE`, message neutre, cause `garde_fou:entree:<scanner>` dans `audit.agent`.
2. **La conception** : neutralisation de ce qui passe l'entrée. Le **code décide** (la décision est forcée par la classe du barème, GF2) ; aucune identité n'est jamais envoyée à un agent ; chaque sortie est contrôlée (GP, GR, GF, GA et LLM Guard `Sensitive`, `Secrets`) ; le LLM ne rédige que des textes, comparés à la référence déterministe, sinon repli. Test `G01` : le jeu hostile et sa réserve, avec une rédaction **qui obéit**, ne changent pas la proposition (`tests/integration/test_jeu_garde_fous.py`, lent, vrais modèles).

Conséquence assumée : un hostile non détecté à l'entrée n'est **pas exécuté**, mais le dossier ne part pas en revue humaine à cause du contrôle d'entrée. L'option « classifieur LLM en complément » est remontée à Acerola (R21), sans décision.

### Comment l'évaluateur vérifie en direct

1. `make garde-fous` (modèles LLM Guard réels, lent) : taux par catégorie et faux positifs sur les quatre jeux.
2. `uv run pytest agentic-cluster/tests/unit/test_injection.py --no-cov` : les 8 injections classiques et les 67 phrases légitimes.
3. En ligne : `PUT /api/contrats/{n}/observations` avec sa propre phrase, puis `POST /v1/souscriptions/{n}/evaluation` : `REVUE_HUMAINE` et message neutre (injection franche), ou fiche en `EN_ANALYSE` (légitime, ou hostile subtil neutralisé). Script complet : `docs/demo-atelier-4.md`.
4. Ni le nom d'un détecteur ni un extrait du texte n'apparaissent dans la réponse (`e2e/test_cluster.py::test_observations_hostiles_revue_humaine_et_message_neutre`).

## 4. Sprint 5 — signaux à surveiller

Liste de la spec § 8. Pour chaque signal : où il est émis **aujourd'hui** (nom vérifié dans le code), et la requête KQL à utiliser **une fois #54 branché**. Les requêtes KQL sont des **propositions non exécutées** : les noms de colonnes d'Application Insights (`Properties`, `AppTraces`, `AppDependencies`) sont à valider au branchement.

Émission aujourd'hui (`agentic-cluster/agentinsurflow_cluster/infrastructure/otel/audit.py`) :
- journal `insurflow.audit`, message `audit.agent`, champs : `trace_id`, `numero_contrat`, `agent`, `mode`, `cause`, `version_prompt`, `garde_fous`, `vue_sha256`, `rapport_sha256`, `duree_ms`, `signal_injection` ;
- span `invoke_agent`, attributs : `gen_ai.agent.name`, `insurflow.mode`, `insurflow.cause`, `insurflow.signal_injection`.
- réglage par agent (`agentic-cluster/agents.toml` : modèle, température, `max_tokens`, délai) : validé au démarrage du cluster et, pour le modèle, au déploiement (existence sur Foundry, lecture seule) ; trace : `audit.agent` / span `invoke_agent` (modèle, température, `max_tokens`, tokens) et `GET /health` (`reglages`).

| Signal | Émis aujourd'hui | KQL (une fois #54 branché) |
|---|---|---|
| Latence p95 par agent | `audit.agent.duree_ms` + `agent` ; durée du span `invoke_agent` | `🔴 à brancher (#54)` : `AppTraces \| where Message == "audit.agent" \| extend agent=tostring(Properties.agent), d=todouble(Properties.duree_ms) \| summarize p95=percentile(d,95) by agent, bin(TimeGenerated,1h)` |
| Latence p95 par évaluation (budget 30 s) | Span HTTP serveur de `POST /evaluations/{n}` (instrumentation FastAPI) ; `🔴 À CONFIRMER` : pas de champ de durée d'évaluation dans `audit.agent` | `🔴 à brancher (#54)` : `AppRequests \| where Name has "evaluations" \| summarize p95=percentile(DurationMs,95) by bin(TimeGenerated,1h)` |
| Coût et jetons par dossier et par agent (SLO-6) | **Non émis par le cluster** : aucun attribut `gen_ai.usage.*` n'est posé. Les jetons du LLM sont mesurés par la **gateway** (`/api/llm`, vérification de la mesure en production : #71, `README.md` racine) | `🔴 à brancher (#54)` : côté gateway, `AppDependencies \| where Properties has "gen_ai.usage" \| …` à écrire après #71 ; côté cluster, attributs `gen_ai.usage.input_tokens` / `output_tokens` à ajouter dans `AuditOtel.tracer` (`🔴 À CONFIRMER`) |
| Taux de repli et de `REVUE_HUMAINE` par cause (SLO-5) | `audit.agent.mode` (`llm`/`repli`) et `cause` ; `insurflow.mode`, `insurflow.cause` | `🔴 à brancher (#54)` : `AppTraces \| where Message == "audit.agent" \| summarize n=count() by mode=tostring(Properties.mode), cause=tostring(Properties.cause)` |
| Taux de refus des garde-fous d'entrée et de sortie | `cause` = `garde_fou:entree:<scanner>` (entrée) ou `garde_fou:<code>` (sortie : `GFn`, `GPn`, `GRn`, `GAn`, scanner) ; `garde_fous` (liste des codes) | `🔴 à brancher (#54)` : `… \| where tostring(Properties.cause) startswith "garde_fou:" \| summarize n=count() by cause=tostring(Properties.cause)` |
| Taux de faux positifs | **Pas en production** : mesuré hors ligne sur le jeu légitime (`make garde-fous`, 0/67). En ligne, les blocages d'un contrat légitime se lisent via la cause ci-dessus | `🔴 à brancher (#54)` : rapprocher `garde_fou:entree:*` des revues finalement `ACCEPTE` (jointure `RAPPORT_AGENT` / `DECISION` en SQL, pas en KQL) |
| Erreurs `llm_ko` | `audit.agent.cause = "llm_ko"` (`application/agents.py`) | `🔴 à brancher (#54)` : `… \| where tostring(Properties.cause) == "llm_ko" \| summarize n=count() by bin(TimeGenerated,1h)` |
| Erreurs `budget` | Cause `duree` (garde globale 25 s) et `precondition` : écrites dans la section d'état (`ETAT` / `SECTION_ETAT`, SQL), **pas** dans `audit.agent` (aucun agent n'a tourné) | `🔴 à brancher (#54)` : SQL sur `ETAT` ; en KQL, seulement la durée de la requête HTTP (ligne « par évaluation ») |
| Erreurs `MCP_INDISPONIBLE` | `ErreurOutil("MCP_INDISPONIBLE")` côté client MCP (`infrastructure/mcp/client.py`) ; l'agent la range en cause `erreur` dans `audit.agent` ; l'API répond `502 OUTIL_INDISPONIBLE`. Côté serveur MCP : attribut `resultat.code` des spans | `🔴 à brancher (#54)` : `AppRequests \| where ResultCode == "502" \| summarize n=count() by bin(TimeGenerated,1h)` ; `cause == "erreur"` dans `audit.agent` |
| Démarrage à froid de LLM Guard | **Pas de durée émise**. Mesuré à la main : ≈ 6 s en local (rapport T12). Visible par `GET /health/cluster` en `503 GARDE_FOUS_EN_CHARGEMENT` tant que les modèles ne sont pas chargés, et par la sonde de démarrage de la Container App (≈ 3 min autorisées) | `🔴 à brancher (#54)` : journaux système de la Container App (`ContainerAppSystemLogs`, `Reason == "ProbeFailed"`) ; une durée de chargement explicite reste à émettre (`🔴 À CONFIRMER`) |

Seuil de décision à fixer au sprint 5 pour chaque signal : `🔴 À CONFIRMER` (aucun seuil n'est promis par le dossier au-delà des SLO-5 et SLO-6).

## 5. Ce qui reste à faire pour clore le contrat

- Jouer les 3 dossiers de référence en staging (K1) et mesurer le délai < 30 s LLM coupé (K5).
- Décider du libellé de K5 (« Service temporairement indisponible » ou message neutre).
- Rejouer K2 par requête sur les traces après le déploiement du cluster (R19), puis en KQL avec #54.
- Démontrer la reprise après redémarrage du cluster (K11).
- 7b : K8 et K10.
- UI et accessibilité : K6 (#38).
