# Rejeu E2E avec un jeton d'utilisateur — 04/11/2026

Écart visé (C9) : le parcours d'évaluation réel, avec échange On-Behalf-Of, n'est pas prouvé par la CI, car une identité d'application ne peut pas faire cet échange.

- **Environnement** : staging, SHA `7b492c1`, gateway et cluster. Heures en UTC.
- **Acteur** : Claude lance `pytest e2e` depuis le poste, avec le jeton Entra du gestionnaire connecté (`az account get-access-token`). Ce rejeu n'est pas dans la CI.
- **Dossiers** : `000004`, `000005`, `000006` et `000002` du gestionnaire connecté ; `000007` d'un autre gestionnaire.

## Résultats

| Passage | Heure | Résultat |
|---|---|---|
| Suite complète, 17 tests | 08:40 à 08:42 | 13 réussis, 4 en échec, aucun sauté |
| Les 4 tests en échec, espacés d'environ 90 s, variable corrigée | 08:44 à 08:48 | 4 réussis |

## Interprétation des 4 échecs du premier passage

| Tests | Échec | Cause | Après correction |
|---|---|---|---|
| `test_contrat_d_un_autre_gestionnaire_404`, `..._via_reponses` | 200 au lieu de 404 | **Erreur de réglage du rejeu** : `E2E_CONTRAT_AUTRE=AIF-2026-000001`, qui appartient au gestionnaire connecté. Ce n'est pas une faille : `000007` répond 404, comme un dossier inexistant | Réussis avec `000007` |
| `test_dossier_complet_en_analyse_puis_revue`, `test_observations_hostiles_revue_humaine_et_message_neutre` | 429 `TROP_DE_REQUETES` | Évaluations enchaînées sans pause : comportement attendu d'une limite de débit, déjà vu le 03/11 | Réussis une fois espacés |

## Ce que le passage prouve

- Évaluation réelle avec On-Behalf-Of : dossier complet en `EN_ANALYSE`, puis revue en `ACCEPTE`.
- Pause puis reprise ; le statut final est bien `EN_ANALYSE` ou `REVUE_HUMAINE`.
- Observations hostiles : `REVUE_HUMAINE`, message neutre, ni cause ni détecteur dans la réponse.
- BOLA par `/api/contrats` et par `/api/reponses` (chemin On-Behalf-Of) : même 404 qu'un dossier inexistant.

## Défaut révélé

Pendant `test_pause_puis_reprise` (réussi), l'Analyste est passé en repli `llm_ko` sur `000004` à 08:41:10, et AL-2 s'est déclenchée à 08:44. Ce test accepte ce repli, il ne l'aurait donc pas signalé seul. Cause probable : délai de 2 s trop court, porté à 4 s par #234.

## Limites

- Lancé à la main depuis un poste, pas à chaque déploiement.
- La suite ne passe pas d'un seul tenant quand les évaluations s'enchaînent : la limite de débit impose de les espacer.
