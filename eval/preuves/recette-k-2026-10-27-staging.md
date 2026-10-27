# Recette des K en staging — 27/10/2026 (soir)

- **Environnement** : staging (`insurflow-staging`), release **v0.6.17**, SHA `c619d0f` (`/health`).
- **Acteurs** : Acerola, gestionnaire B, pilote l'espace gestionnaire (`/app/`). Claude vérifie en **lecture seule** :
  - `GET /api/contrats/{n}/etat`, `/souscripteur` et `/v1/souscriptions/{n}/contrat` ;
  - `GET /api/traces/{trace_id}` ;
  - journaux des Container Apps (Log Analytics) et Application Insights de la Function de calcul.
- **Données** : seed fictif (dossiers `AIF-2026-0000NN`). Aucune donnée réelle.
- **Heures en UTC.** Les durées des agents sont celles des spans `invoke_agent`.

## Synthèse

| K | Dossier | Résultat | Preuve |
|---|---|---|---|
| K1 acceptable | 000001 | ✅ `ACCEPTE`, `tous_risques`, 819,73 €/an | § K1 |
| K1 refus | 000010, 000006 | ✅ `REFUSE` R01_SUSPENSION, puis `REFUSE` R02_RESILIATIONS | § K1 |
| K1 limite | — | ⬜ non joué (le barème n'a pas de classe « limite ») | — |
| K3 BOLA | 000007 (gestionnaire C) | ✅ 404 | § K3 |
| K4 validation humaine | 000001 | ✅ `EN_ANALYSE` → `ACCEPTE`, contrat imprimé | § K4 |
| K5 LLM coupé | 000004 | ✅ « Service temporairement indisponible », `REVUE_HUMAINE`, ~10 s | § K5 |
| K6 clavier seul | 000006 | ✅ sauf « Tchat corpus » (corrigé par #147, à revérifier) | § K6 |
| K7 prime déterministe | 000001, 000005 | ✅ prime juste, Actuaire en repli `llm_ko` | § K7 |
| K8 / K10 relances bornées, sans suite | 000003 | ✅ 3 relances, plus de 4ᵉ, `SANS_SUITE` | § K8 |
| K11 reprise après redémarrage | 000005 | ✅ même tentative, reprise au Rédacteur | § K11 |

Défauts trouvés et corrigés pendant la recette (PR en brouillon, à fusionner après la recette) :
- **#146** : délais de l'évaluation (démarrage à froid du calcul, appels MCP, Actuaire) ;
- **#147** : navigation au clavier de l'en-tête ;
- **#145** : visionneuse du contrat (amélioration demandée).

## K1 — Décision homogène et justifiée

**000001, acceptable.** Trace `1f5f46fa564ac39f07f76536e0794659`, tentative 1.

| Agent | Mode | Tokens (entrée / sortie) | Span |
|---|---|---|---|
| Pièces | llm | 262 / 22 | 3,96 s |
| Analyste | llm | 277 / 66 | 4,92 s |
| Rédacteur | llm | 1 629 / 83 | 3,71 s |
| Actuaire | repli `llm_ko` | 0 / 0 | 2,64 s |

Proposition : `ACCEPTE`, `tous_risques`, prime de 819,73 €/an (68,31 €/mois).

**000010, refus.** Il a fallu trois tentatives.
- **Tentative 1** (22:13:50 → 22:14:17) : la Saga atteint sa garde globale **avant le premier rapport**, d'où `REVUE_HUMAINE` « Délai d'analyse dépassé ». Le serveur MCP n'a reçu aucun appel d'outil pendant 26 s après la lecture du dossier. Le blocage est côté cluster, avant l'appel MCP ; la cause supposée est le jeton OBO.
- **Tentative 2**, trace `92a986f17eebe76560c90ee03fb63f53` : Pièces passe en llm (1,44 s), puis l'Analyste tombe en repli `erreur` au bout de 10,3 s. Le serveur MCP a appelé le calcul (`evaluer_risque`), qui n'a pas répondu dans son délai de 10 s. Application Insights ne montre **aucune requête reçue** par la Function : c'est un démarrage à froid (Flex Consumption, 23 min sans appel).
- **Tentative 3**, trace `07006ef5edc9e12c668d191316a7b909` : Pièces (262 / 22), Analyste (284 / 89) et Rédacteur (4 890 / 130) passent tous en llm. Proposition : **`REFUSE`, règle `R01_SUSPENSION`, citation `PI-R01_SUSPENSION`**. Validée par le gestionnaire, puis `GET …/contrat` → `409 CONTRAT_NON_ACCEPTE`, comme attendu.

**000006, refus.** Trace `1efc1daffa5da4e0d51542b0e02897f0`. Les trois agents passent en llm. Proposition : **`REFUSE`, formule `tiers`, règle `R02_RESILIATIONS`**, validée au clavier (voir K6).

## K3 — BOLA

`GET /api/contrats/AIF-2026-000007/souscripteur` avec le jeton du gestionnaire B répond **404**, comme pour un contrat inexistant. 000007 appartient au gestionnaire C.

## K4 — Validation humaine

000001 passe de `EN_ANALYSE` à `ACCEPTE` après validation avec motif. Le contrat généré, `GET /v1/souscriptions/AIF-2026-000001/contrat`, est cohérent avec l'impression :
- souscripteur : `Nom1`, téléphone `0600000001`, permis `FR` ;
- véhicule : VIN `VIN00000000000001`, mis en circulation le 01/05/2019, stationnement `garage` ;
- 6 garanties de la formule `tous_risques`, avec leurs franchises :

  | Garantie | Franchise |
  |---|---|
  | `responsabilite_civile` | 300 |
  | `protection_juridique` | 0 |
  | `vol_incendie_tempete` | 300 |
  | `bris_de_glace` | 0 |
  | `dommages_tous_accidents` | 450 |
  | `assistance_0_km` | — |

- prime : 819,73 €/an (68,31 €/mois), effet au 01/01/2026.

## K5 — Résilience (LLM coupé)

`make recette ACTION=llm-off` crée la révision `ai-cluster-staging--0000024` (`INSURFLOW_LLM_ACTIF=false`). L'évaluation n'est lancée qu'une fois cette révision **prête et à 100 % du trafic**.

Résultat sur **000004**, trace `37a266e88224d6fec0346317b8665382` :

| Agent | Mode | Tokens | Rapport |
|---|---|---|---|
| Pièces | repli `llm_ko` | 0 | 22:49:39,95 |
| Analyste | repli `llm_ko` | 0 | 22:49:42,69 |
| Rédacteur | repli `llm_ko` | 0 | 22:49:43,01 |

- Message affiché : **« Service temporairement indisponible »**.
- Statut `REVUE_HUMAINE`. La règle `R01_SUSPENSION` est identifiée par le barème, sans LLM.
- Temps affiché : **10 s**, sous le seuil de 30 s.

Puis `llm-on` crée la révision `0000025` (`true`), prête et à 100 % du trafic.

**Écart de procédure, première tentative sur 000002.** `llm-off` (révision `0000022`, créée à 22:42:28) rend la main avant que la révision reçoive le trafic. 000002 a donc été évalué à 22:42:51 par l'ancienne révision, LLM actif. Ce n'est pas un défaut du code : il faut attendre l'activation de la révision avant de lancer l'évaluation.

## K6 — Parcours au clavier seul

Sur 000006, sans souris, sont atteignables et utilisables :
- ouvrir le dossier avec Entrée ;
- lancer l'évaluation ;
- les sous-onglets aux flèches ;
- la saisie du motif ;
- la validation.

**Seule exception : « Tchat corpus »**, dans l'en-tête, n'est pas atteignable avec Tab. L'en-tête suivait le motif d'onglets ARIA : seul l'onglet actif est en `tabindex="0"`, l'autre en `-1`. **#147** le remplace par des liens de navigation simples. À revérifier après déploiement.

## K7 — Prime déterministe

L'Actuaire passe en repli `llm_ko` sur 000001 et 000005 : son `delai_s` de 1,5 s est plus court que le temps de réponse du modèle, 3 à 5 s. La prime reste celle de la Function de calcul (819,73 € pour 000001), ce qui est exactement le comportement visé par K7. #146 porte ce délai à 4 s.

## K8 / K10 — Relances bornées et fin de parcours

000003 manque d'une pièce (`releve_information`, statut `incomplet`), d'où `REVUE_HUMAINE` « Pièces incomplètes ». Ensuite :
- 3 relances sont envoyées depuis `/app/`, et l'interface ne propose plus de 4ᵉ relance ;
- « Classer sans suite » donne **`SANS_SUITE`, `nb_relances = 3`**.

Le refus d'une 4ᵉ relance côté API (`409 RELANCES_EPUISEES`) n'est pas rejoué en staging. Il est couvert par `RelancesTests.cs::Trois_relances_puis_409`.

Observé en passant :
- **limite de débit de la gateway** : des relances de l'évaluation en rafale reçoivent un `429` « Trop de requêtes » (#122) ;
- **garde-fou GP2** : une sortie du LLM de Pièces incohérente avec la référence est écartée au profit de la référence (`garde_fou:GP2`, tentatives 4 et 5).

## K11 — Reprise après redémarrage du cluster

Sur 000005, tentative 1 :

| Heure | Événement | Trace |
|---|---|---|
| 22:36:55 | Pièces (llm) | `437a773670e3f5ba5b15eef54fe148aa` |
| 22:36:58 | Analyste (llm), puis **Pause** | `437a773670e3f5ba5b15eef54fe148aa` |
| 22:37:43 | **Nouvelle réplique** `ai-cluster-staging--0000021-5b4597674f-qs2v8` (`make recette ACTION=redemarrer`) | — |
| 22:38:01 | Rédacteur (llm), **même tentative 1** | `514a8955abfd21739883c4145b3827fb` |
| 22:38:04 | Actuaire, puis `EN_ANALYSE`, validé (`ACCEPTE`) | `514a8955abfd21739883c4145b3827fb` |

La reprise se fait au point de pause, depuis les points de reprise PostgreSQL, sans nouvelle tentative et sans rejouer Pièces ni l'Analyste.

## Défauts trouvés

| Constat | Cause | Correctif |
|---|---|---|
| 000010, tentative 1 : 27 s sans rapport d'agent | Appel MCP du cluster sans limite (jeton OBO via `to_thread`, httpx à 30 s) | #146 : `DELAI_APPEL_S = 22 s` → repli `erreur` tracé |
| 000010, tentative 2 : Analyste en repli `erreur` | Démarrage à froid de la Function de calcul, plus long que les 10 s du client MCP | #146 : délai à 20 s, et une instance toujours prête (`infra/calcul.sh` ①b, **appliquée le 28/10** : 1 instance `http`, staging et production) |
| Actuaire toujours en repli `llm_ko` | `delai_s = 1.5` | #146 : 4 s |
| « Tchat corpus » inatteignable au clavier | Motif d'onglets ARIA pour des liens de page | #147 |
| `llm-off` / `llm-on` rendent la main trop tôt | `az containerapp update` n'attend pas l'activation de la révision | #149 (fusionnée le 28/10) : `recette.sh` attend la révision prête et à 100 % du trafic |
