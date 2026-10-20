# RGPD — applicabilité, minimisation, registre, procédures de tri

*Livrable L8 · compétence C4. Spec §2.2, §5.3, §9.4.*

## Applicabilité

- **Corpus (Code des assurances)** : textes de loi publics, **aucune donnée personnelle** → RGPD non applicable.
- **Dossiers** : données personnelles par nature (identité, adresse, permis, sinistres). Au sprint 3, elles sont
  **fictives** (seed), mais traitées comme réelles :
  - **minimisation** : l'agent et l'API ne lisent que `vue_contrat_minimisee` (tranche d'âge au lieu de la date
    de naissance, département au lieu de l'adresse, aucun nom ni numéro de permis) ;
  - **moindre privilège** : le compte `dossiers` n'a de droit que sur la vue ;
  - **BOLA** : un gestionnaire ne voit que ses contrats (`gestionnaire_id` = `oid` du jeton) ; un contrat d'un
    autre répond comme un contrat inexistant (404).
- **Questions posées à l'agent** : jamais stockées en clair ; les traces n'en gardent que le sha256 et la longueur.

## Registre des traitements

| Traitement | Finalité | Données | Base légale | Destinataires | Conservation |
|---|---|---|---|---|---|
| Consultation des dossiers par l'agent | Aide à la souscription | Vue minimisée du contrat | Exécution du contrat | Gestionnaire du contrat | 🔴 à décider |
| Corpus réglementaire | Réponses citées | Textes de loi (pas de donnée personnelle) | — | Gestionnaires | Tant qu'en vigueur ; versions obsolètes marquées |
| Traces techniques | Exploitation, preuve de l'ancrage | `trace_id`, routes, statuts, sha256 de la question, `client.address` (IP) | Intérêt légitime | Gestionnaires (puis DSI) | 🔴 à décider ; base vidée à chaque déploiement au S3 |
| Journal des ingestions | Preuve et rejouabilité | Rapports (comptes, raisons de rejet) | Intérêt légitime | Équipe | Versionné dans `eval/preuves/` |

## Procédures de tri

| Procédure | Quoi | Automatique ? | Fréquence |
|---|---|---|---|
| Vidage de la base annexe | Toutes les bases (vecteurs, dossiers, traces) | Oui (base éphémère) | À chaque déploiement |
| Réextraction Légifrance | Nouvelles versions ; anciennes marquées `obsolete` | Non (`make extraire`) | 🔴 à décider |
| Purge des spans | Spans plus anciens que N jours | Non au S3 | 🔴 à décider |
| Questions de l'agent | Non conservées hors traces techniques (sha256 seulement) | — | — |

**Hors périmètre** : la purge RGPD automatisée ; les procédures sont rédigées, les durées restent à décider
par Acerola (point ouvert de la spec).
