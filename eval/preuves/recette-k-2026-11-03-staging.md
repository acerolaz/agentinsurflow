# Recette des K en staging — 03/11/2026

- **Environnement** : staging (`insurflow-staging`), release **v0.6.33**, SHA `919aac8`.
- **Acteurs** : Claude pilote l'espace gestionnaire avec Playwright, au clavier, dans une fenêtre où Acerola s'est connecté (MFA comprise). Acerola lance les écritures Azure (`make recette`), joue le parcours 1 au clavier et relit le contrat imprimé.
- **Vérifications en lecture seule** : réponses HTTP vues par le navigateur, `GET …/contrat`, Application Insights, révisions Container Apps.
- **Données** : seed fictif remis à zéro par le déploiement. Aucune donnée réelle.
- **Heures en UTC.**
- **Captures** : hors dépôt (elles montrent le nom du compte), dans `Exam/preuves-2026-11-03/`.
- Le script Playwright n'est pas versionné et ne tourne pas en CI : il prouve cette recette, pas les versions suivantes.

## Synthèse

| K | Dossier | Résultat | Preuve |
|---|---|---|---|
| K1 acceptable | 000001 | ✅ `ACCEPTE`, `tous_risques`, 819,73 €/an | § K1 |
| K1 refus | 000010 | ✅ `REFUSE` `R01_SUSPENSION`, `/contrat` en 409 | § K1 |
| K1 limite (hors barème) | 000011 | ✅ `REVUE_HUMAINE`, motif « Donnée hors barème : crm. Revue humaine requise. » | § K1 |
| K3 BOLA | 000007 | ✅ « Contrat introuvable » (404) | § K6, parcours 10 |
| K4 validation humaine | 000001 | ✅ `EN_ANALYSE` → `ACCEPTE`, contrat en 200 | § K1 |
| K5 LLM coupé | 000002 | ✅ message, score, 11,2 s | § K5 |
| K6 clavier seul | plusieurs | ✅ 15 parcours, deux réserves | § K6 |
| K8 / K10 relances bornées | 000003 | ✅ 3 relances, 4ᵉ en 409, `SANS_SUITE` | § K6, parcours 12 et 13 |
| K9 audit | 8 évaluations | 🟡 `audit.*` prouvés en KQL ; Application Map et Live Metrics non démontrés | § K9 |
| K11 reprise après redémarrage | 000004 | ✅ reprise à l'Analyste, sans rejouer les Pièces | § K11 |

K2 et K7 n'ont pas été rejoués.

## K1 et K4

| Heure | Dossier | Événement | `trace_id` |
|---|---|---|---|
| 11:33:21 | 000010 | Fiche `REFUSE`, `R01_SUSPENSION`, évaluation en 20,9 s | `59dbe50a348f29d75b39f24e7bf519db` |
| 11:33:52 | 000010 | Seul bouton : « Valider le refus » ; revue en 200, statut `REFUSE` | même trace |
| 11:34:10 | 000001 | Fiche `ACCEPTE`, 819,73 € par an, soit 68,31 € par mois, évaluation en 16,0 s | `1d7bd34f8fd1598d319dbda05326aa04` |
| 11:34:40 | 000001 | « Valider » ; revue en 200, statut `ACCEPTE`, contrat en 200 | même trace |
| 11:34:51 | 000011 | `REVUE_HUMAINE`, hors barème, évaluation en 5,8 s | `d509177d0c834273df530914d4e8083a` |
| 11:35:20 | 000010, 000011 | `GET …/contrat` : 409 `CONTRAT_NON_ACCEPTE` | — |

Le défaut du 02/11 (`000010` accepté sans prime, contrat aux montants vides) ne se reproduit pas : #215.

## K5

Coupure vérifiée : `INSURFLOW_LLM_ACTIF=false` sur la révision active, et aucun appel de chat à la gateway pendant le premier essai (10:50 à 10:59).

| Heure | Essai | Résultat | `trace_id` |
|---|---|---|---|
| 10:58:04 | Acerola, `000002` | `REVUE_HUMAINE`, `llm_ko` ; score absent de l'écran : corrigé par #216 | `68ce1ddb…` |
| 13:23:13 | Playwright, `000002`, après #216 | HTTP 200 en 11,2 s ; écran : « Service temporairement indisponible. Score : 0 » | `ac1e6c353c4698d49646ed5803ca0f94` |

Le score de 0 est celui du barème : section `risque` « Risque acceptable, score 0 », `bareme-2026.10-v1`.

## K6 : parcours au clavier

Détail ligne à ligne : [`espace-gestionnaire.md`](../../docs/espace-gestionnaire.md), § Accessibilité. Réserves :

- **Parcours 14** : le motif gardé est prouvé ; le curseur stable pendant une évaluation n'a pas été testé.
- **Parcours 13** : la confirmation s'affiche ; elle a été acceptée par script, car le navigateur la fermait seul sous Playwright.

Le lecteur d'écran n'est pas couvert ici : il se vérifie avec VoiceOver.

## K9 : audit dans Application Insights

Depuis le déploiement (`appi-insurflow-staging`, après 11:15) : **8** `audit.evaluation`, **19** `audit.agent`, **4** `garde_fous.chargement`. #176 est donc prouvée **en staging**. Une évaluation tracée en production reste à jouer : voir [`recette-c11-2026-11-03.md`](recette-c11-2026-11-03.md).

## Tokens de sortie (#71)

Recette du 02/11 sur v0.6.31 : 21 appels de chat depuis le déploiement, 21 mesurés avec leurs tokens de sortie, 0 `non_disponible`. Le 03/11, le détail d'une étape affiche bien entrée et sortie (Analyste de `000001` : 277 + 58 = 335 tokens).

## K11

| Heure | Événement | `trace_id` |
|---|---|---|
| 13:26:28 | `000004` : Pièces faites, **Pause** (202) ; statut `EN_PAUSE` | `73c08ab14c42032093029f6f9bbc4f19` |
| — | `make recette ACTION=redemarrer` (Acerola) | — |
| 13:29:07 | Page rechargée : Pièces « fait », Analyste « à venir », bouton « Reprendre » | — |
| 13:29:28 | Reprise en 21,0 s : Analyste et Rédacteur joués, Pièces non rejouées | `cc755a84a53bd6e8bf016e554e65907e` |

La reprise est prouvée. L'évaluation finit en `REVUE_HUMAINE`, cause `garde_fou:GF4`, score 1 : le garde-fou a rejeté la sortie du Rédacteur, indépendamment de la reprise. Une autre évaluation de `000004` passe en `EN_ANALYSE` à 13:31:29 (`16494fabe28aa34a778d1008c8de2ae3`) : elle ne vient pas de cette recette et son origine n'est pas établie.

## Défauts et réserves constatés

| Constat | Détail | Suite |
|---|---|---|
| **Tchat bloqué 30 s, deux fois** | 10:11:34 (`llm.completer`) et 10:16:04 (`embeddings.vectoriser`), `APITimeoutError` côté rag, aucune trace de ces appels côté gateway. Non reproduit ensuite. Cause non établie. | #218 : embeddings à 15 s avec un second essai ; chat non traité |
| **Marge du tchat faible** | Chat de rag sur Kimi-K2.5 : médiane ≈ 8 s, p95 ≈ 22 s ; limite de 30 s, sans nouvelle tentative. | #218 : changer de modèle est une décision d'Acerola |
| **`llm_ko` avec le LLM actif** | Agent Pièces en repli à 09:56, 10:15, 11:35 et 13:26 ; AL-2 déclenchée hors coupure (09:59, 10:19, 11:39). **Cause, établie après la recette** : garde de 1,5 s pour des appels de ≈ 1,3 s (p90 ≈ 4,7 s). À 11:35, l'appel démarre 0,57 s après l'agent et dure 1,43 s, côté gateway en 200 : la garde coupe avant. Le cas de 13:26 (0,38 s, aucun appel à la gateway, pendant une pause) n'est pas expliqué par cette garde. | #219 : garde portée à 4 s |
| **Question de démonstration refusée** | « Quelles pièces pour souscrire une assurance auto ? » → refus, verrou 3, avec `NP-JEUNES-CONDUCTEURS` en tête de la recherche. **Cause probable** : seules les citations d'articles (`[L211-1]`) étaient reconnues, pas `[NP-…]` ni `[PI-…]`. | #220 : citations reconnues, à vérifier après déploiement |
| **`000011` non clôturable** | Pas de formulaire de revue en `REVUE_HUMAINE` : seuls « Lancer » et « Pause » sont proposés. | #221 : refus motivé possible |
| **Message de revue humaine fugace** | Le message et le score disparaissent au rechargement de la page. | Connu (#216) |

## Rejeu après #223 (staging, SHA `d7b5d87`, 15:49 à 15:55 UTC)

Le tchat est encore sur Kimi-K2.5 ; `gpt-4.1-mini` arrive avec #224.

| Point | Résultat | Preuve |
|---|---|---|
| #221 `000011` | « Refuser » seul, motif, revue en 200, `REFUSE`, « Lancer » désactivé, `/contrat` en 409 | `ab406e2f3603…` |
| #221 `000003` (pièces manquantes) | aucun bouton de revue : le parcours reste relances, puis sans suite | `5208fff32198…` |
| #219 agent Pièces | 6 évaluations en mode `llm`, 0 `llm_ko`, aucune alerte active dans l'heure | `audit.agent` |
| #220 question de démonstration | réponse en 12,4 s, citation `NP-JEUNES-CONDUCTEURS` : **les notices scrapées sont citées** | tchat |
| Propositions | `000001`, `000002`, `000004`, `000010` en `EN_ANALYSE`, 12 à 17 s | `489b97b57390…`, `73156206046b…`, `29fc7920e45f…`, `d9b6b1b02106…` |

**Ce qui reste ouvert :**
- « Que couvre la formule tous risques ? » est refusée au verrou 3, alors que `NP-TOUS-RISQUES` arrive en tête de la recherche : suivi séparé.
- Blocage de 30 s (#218) : non reproduit sur ce rejeu, cause toujours non établie.
- Quatre évaluations lancées à la suite ont reçu un 429 de la limite de débit : comportement attendu, espacées d'une minute elles passent.

