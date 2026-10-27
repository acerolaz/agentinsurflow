# RGPD — applicabilité, minimisation, registre, procédures de tri

*Livrable L8 · compétence C4. Spec §2.2, §5.3, §9.4.*

## Applicabilité

- **Corpus (Code des assurances)** : textes de loi publics, **aucune donnée personnelle** → RGPD non applicable.
- **Dossiers** : données personnelles par nature (identité, adresse, permis, sinistres). Au sprint 3, elles sont
  **fictives** (seed), mais traitées comme réelles :
  - **minimisation** : l'agent et l'API ne lisent que `vue_contrat_minimisee` (tranche d'âge au lieu de la date
    de naissance, département au lieu de l'adresse, aucun nom ni numéro de permis) ;
  - **moindre privilège** : le compte `dossiers` n'a de droit que sur la vue ;
  - **exception du contrat imprimé** (décision d'Acerola, 27/10, sur son modèle de contrat) : `GET …/contrat` lit les
    parties au contrat (nom, prénom, date de naissance, adresse, téléphone, e-mail, permis, véhicule) par
    `vue_contrat_accepte` et les garanties par `vue_garanties_contrat_accepte`, pour les seuls contrats `ACCEPTE` du
    gestionnaire ; jamais dans une trace ni vers le cluster ou un LLM. Le contrat imprimé porte la notice RGPD
    (articles 13 et 14). La table `souscripteur` reste fermée au compte `dossiers` ;
  - **exception de la fiche du lead** (décision d'Acerola, 27/10) : `GET …/souscripteur` lit civilité, nom, prénom,
    adresse, mobile, e-mail et véhicule par `vue_fiche_souscripteur`, pour les seuls contrats du gestionnaire, et les
    affiche en tête du détail du dossier ; jamais dans une trace ni vers le cluster ou un LLM ;
  - **BOLA** : un gestionnaire ne voit que ses contrats (`gestionnaire_id` = `oid` du jeton) ; un contrat d'un
    autre répond comme un contrat inexistant (404).
- **Questions posées à l'agent** : jamais stockées en clair ; les traces n'en gardent que le sha256 et la longueur.

## Registre des traitements

| Traitement | Finalité | Données | Base légale | Destinataires | Conservation |
|---|---|---|---|---|---|
| Consultation des dossiers par l'agent | Aide à la souscription | Vue minimisée du contrat | Exécution du contrat | Gestionnaire du contrat | 🔴 à décider |
| Édition du contrat accepté | Conditions particulières remises à l'assuré | Identité, adresse, téléphone, e-mail, permis, véhicule, garanties (`vue_contrat_accepte`, `vue_garanties_contrat_accepte`) | Exécution du contrat | Gestionnaire du contrat | 🔴 à décider |
| Fiche du lead (détail du dossier) | Contacter le souscripteur pendant l'instruction | Civilité, identité, adresse, mobile, e-mail, véhicule (`vue_fiche_souscripteur`) | Mesures précontractuelles | Gestionnaire du contrat | 🔴 à décider |
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
