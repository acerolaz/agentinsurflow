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
| Consultation des dossiers par l'agent | Aide à la souscription | Vue minimisée du contrat | Exécution du contrat | Gestionnaire du contrat | Aucune copie hors du dossier : suit la durée du dossier (lignes suivantes) |
| Édition du contrat accepté | Conditions particulières remises à l'assuré | Identité, adresse, téléphone, e-mail, permis, véhicule, garanties (`vue_contrat_accepte`, `vue_garanties_contrat_accepte`) | Exécution du contrat | Gestionnaire du contrat | Durée du contrat + 2 ans (prescription biennale, art. L114-1 du Code des assurances) |
| Fiche du lead (détail du dossier) | Contacter le souscripteur pendant l'instruction | Civilité, identité, adresse, mobile, e-mail, véhicule (`vue_fiche_souscripteur`) | Mesures précontractuelles | Gestionnaire du contrat | Dossier non abouti (`REFUSE`, `SANS_SUITE`) : 3 ans après le dernier contact (CNIL, prospects) ; dossier accepté : celle du contrat |
| Mémoire du dossier (cluster d'agents) | Reprise et audit de l'évaluation (K11) | Statut, rapports des agents, sections d'état, tours de pilotage (`etat_dossier`, `rapport_agent`, `section_etat`, `tour_pilotage`) ; construits sur la vue minimisée, aucune identité (K2) | Mesures précontractuelles | Gestionnaire du contrat | Celle du dossier |
| Relances des pièces manquantes | Obtenir les pièces du dossier (K8, trois au plus) | Texte du courriel (peut nommer le souscripteur), pièces demandées, `oid` du gestionnaire (`relance`) ; jamais tracé (la trace porte le rang et la pièce) | Mesures précontractuelles | Gestionnaire du contrat | Celle du dossier |
| Corpus réglementaire | Réponses citées | Textes de loi (pas de donnée personnelle) | — | Gestionnaires | Tant qu'en vigueur ; versions obsolètes marquées |
| Traces techniques | Exploitation, preuve de l'ancrage | `trace_id`, routes, statuts, sha256 de la question, `client.address` (IP) | Intérêt légitime | Gestionnaires (puis DSI) | 30 jours dans Application Insights (rétention de l'espace Log Analytics, lue le 29/10) ; base `traces` annexe vidée à chaque déploiement |
| Journal des ingestions | Preuve et rejouabilité | Rapports (comptes, raisons de rejet) | Intérêt légitime | Équipe | Versionné dans `eval/preuves/` |

## Procédures de tri

| Procédure | Quoi | Automatique ? | Fréquence |
|---|---|---|---|
| Vidage de la base annexe | Toutes les bases (vecteurs, dossiers, traces) | Oui (base éphémère) | À chaque déploiement |
| Réextraction Légifrance | Nouvelles versions ; anciennes marquées `obsolete` | Non (`make extraire`) ; Function mensuelle prévue (#68) | Mensuelle |
| Purge des spans | Spans plus anciens que 30 jours | Oui (rétention Log Analytics) | Continue |
| Purge des dossiers échus | Dossiers non aboutis de plus de 3 ans, contrats échus depuis plus de 2 ans, avec leur mémoire et leurs relances (suppression en cascade) | Non (requête SQL relue par le DPO) | Annuelle |
| Questions de l'agent | Non conservées hors traces techniques (sha256 seulement) | — | — |

**Durées** proposées le 29/10 (#53), à valider par Acerola. Les données du MVP sont fictives (seed) : aucune
purge réelle n'a encore lieu de s'appliquer. **Hors périmètre** : l'automatisation de la purge des dossiers échus.
