# O7 — GLM Poisson (freMTPL2) : deuxième implémentation du scoring

*Spec de la session S5 du sprint 5 — 28/10/2026. Découpage : [`2026-10-28-sprint5-sessions.md`](2026-10-28-sprint5-sessions.md). Indépendante. Issue #155.*

## 1. Intention

Ajouter, **à côté du barème déterministe**, un modèle statistique entraîné : un GLM de Poisson de la **fréquence de sinistres**, appris sur le jeu public **freMTPL2** (assurance auto française). Ce n'est pas une fonction attendue par le brief du sprint 5. C'est la matière des compétences **C12** (tests automatisés du modèle : données, préparation, entraînement, évaluation) et **C13** (chaîne de livraison continue du modèle, MLOps), évaluées dans le rapport de certification. Le dossier le plaçait en V2 (D42) ; Acerola l'intègre au sprint (D-V13).

## 2. Objectifs

1. **Entraînement reproductible** : téléchargement de freMTPL2 (source publique, version et somme de contrôle notées), préparation, entraînement du GLM de Poisson avec exposition en *offset* (`log(Exposure)`), évaluation sur un jeu de test tenu à part.
2. **Métriques du modèle** : déviance de Poisson moyenne et D² (part de déviance expliquée) sur le test ; courbe de Lorenz et Gini ; calibration (fréquence prédite et observée par décile). Comparaison à un **modèle nul** (fréquence moyenne).
3. **Tests automatisés (C12)**, à chaque étape :
   - schéma et bornes des données ;
   - préparation sans fuite (le test ne voit jamais l'entraînement) ;
   - l'entraînement converge et est déterministe à graine fixée ;
   - seuils de qualité : le modèle **bat le modèle nul**, et D² ≥ un seuil **mesuré à la première exécution** puis figé. Le seuil n'est pas inventé : il vaut la valeur obtenue moins une marge, notée avec sa mesure.
4. **Versionnement** : un artefact identifié (`glm-freq-<date>-v<n>`), accompagné de ses métriques, de la version des données et du commit d'entraînement (une fiche du modèle en Markdown).
5. **Exposition** : une API qui renvoie la **fréquence prédite** pour un profil, **à côté** du barème, sans rien changer à la décision ni à la prime (voir §6).
6. **Livraison continue (C13)** : un job de `ci-cd.yml` (ou un workflow dédié) enchaîne données → tests → entraînement → évaluation → porte de qualité → empaquetage → déploiement. Le modèle n'est déployé que si la porte passe.
7. **Suivi dans la vigie** : les métriques hors ligne du modèle publiées avec l'artefact. En ligne : nombre d'appels, latence, et distribution des fréquences prédites, sur une tuile du tableau de bord de S2.

## 3. Non-objectifs

- Remplacer le barème, ou modifier une décision, une prime, ou le parcours du gestionnaire.
- Un modèle de **sévérité** (coût moyen) ou de prime pure complète : fréquence seulement.
- Une plateforme MLOps lourde (Azure ML, MLflow serveur) : pas pour un seul modèle (décision §6).

## 4. Anti-objectifs

- Une donnée personnelle réelle dans l'entraînement ou les traces : freMTPL2 est anonyme et public. Les profils envoyés à l'API passent par la vue minimisée existante.
- Un modèle « qui marche » mais dont le seuil de qualité a été choisi pour passer.
- Une prédiction GLM présentée au gestionnaire comme une décision.

## 5. Contraintes

- Python, hexagonal : le domaine (profil, prédiction) ne dépend ni de `statsmodels` ni de `scikit-learn`. L'adapter de modèle est dans `infrastructure/`.
- Dépendances accordées le 28/10 : `scikit-learn` et `pandas` (§6).
- freMTPL2 : la source exacte (OpenML, ou le paquet R `CASdatasets`) et sa licence sont à noter dans la fiche du modèle.
- Correspondance des variables : celles de freMTPL2 (`DrivAge`, `BonusMalus`, `VehPower`, `VehAge`, `VehBrand`, `VehGas`, `Area`, `Density`, `Region`) ne correspondent pas toutes aux champs d'un dossier AgentInsurFlow. Une **table de correspondance** est à écrire. Les variables sans équivalent sont exclues du modèle, et la fiche le dit.
- Gel des fusions du 29/10 au matin à la fin de la démo du 30/10.

## 6. Décisions d'Acerola (28/10)

1. **Rôle : comparaison seulement.** Une API à part. La fréquence prédite apparaît dans les métriques, jamais dans la décision, la prime ou le rapport de l'Actuaire.
2. **Emplacement : dans `fonction-calcul`**, à côté du barème (*suggestion* de route : `/api/calcul/frequence`). Il est déjà derrière la gateway, avec App Insights et une instance toujours prête.
3. **Registre : un fichier versionné dans l'image de la Function**, avec sa fiche du modèle.
4. **Dépendances : `scikit-learn` (`PoissonRegressor`) et `pandas`**, en dernière version stable figée. `statsmodels` est écarté.

## 7. Preuves de fin de session

1. Les tests C12 sont verts en CI et le rapport d'évaluation est joint au run.
2. L'artefact et sa fiche sont versionnés. Les métriques montrent le gain sur le modèle nul.
3. Le job C13 a déployé le modèle en staging, et un appel de l'API passe par la gateway.
4. La tuile du modèle est visible sur le tableau de bord, et le dossier de conception est amendé : D42 passe de V2 au sprint 5.

## 7 bis. Précisions issues de la relecture (28/10, *mes choix*)

- **Correspondance des variables** (lue dans `fonction-calcul/agentinsurflow_calcul/domain/models.py`) :

  | Champ freMTPL2 | Champ du dossier | Correspondance |
  |---|---|---|
  | `BonusMalus` | `crm` | `crm` × 100 |
  | `VehPower` | `puissance_fiscale_cv` | directe, bornée au domaine de freMTPL2 |
  | `Region` | `departement` | table département → région (anciennes régions de freMTPL2) |

  Les variables `DrivAge`, `VehAge`, `VehBrand`, `VehGas`, `Area` et `Density` n'ont pas d'équivalent dans le dossier. Par exemple, `anciennete_permis_mois` n'est pas un âge. Elles sont donc **exclues**.

  Le modèle est entraîné sur ces 3 variables seulement. C'est une limite assumée, écrite dans la fiche : l'objet de S5 est la chaîne C12/C13, pas la précision du produit. `BonusMalus` est la variable la plus prédictive de freMTPL2 ; si le modèle ne bat pas le modèle nul, le constructeur le signale **avant** d'aller plus loin.
- **Entrée de l'API** : un **profil** envoyé par l'appelant (`crm`, `puissance_fiscale_cv`, `departement`), sur le modèle du barème. Aucun numéro de contrat n'est résolu. Même protection par la gateway que `/api/calcul`.
- **Entraînement en CI** :
  - freMTPL2 est **figé** : fichier téléchargé une fois, version et somme SHA-256 notées, mis en cache dans la CI.
  - Le réentraînement ne se fait **que si le code du modèle ou les données changent** (filtre de chemins, comme le job `changements` de `ci-cd.yml`).
  - Le temps du run ne grossit pas autrement.
- **Tuile du tableau de bord** : S5 l'ajoute à `infra/vigie/dashboard.json` **après la fusion de S2** (rebase). C'est la seule dépendance de S5.

## 8. Laissé au constructeur

- La préparation : regroupements de modalités, plafonnements (`BonusMalus`, `Exposure` ≤ 1), transformation de `Density`.
- La graine, la proportion entre entraînement et test, la marge du seuil D².
