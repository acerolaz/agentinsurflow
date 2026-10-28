# O7 — GLM Poisson freMTPL2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** un GLM de Poisson de la fréquence de sinistres, entraîné sur freMTPL2 (3 variables), testé à chaque étape (C12), livré par la CI derrière une porte de qualité (C13) et exposé par `fonction-calcul` à côté du barème, sans rien changer à la décision ni à la prime.

**Architecture :** l'entraînement (`fonction-calcul/entrainement/`, scikit-learn + pandas, hors de la Function) produit un **artefact JSON** (coefficients, version, données, métriques) versionné dans `agentinsurflow_calcul/modeles/` avec sa fiche Markdown. La Function prédit **en Python pur** (`domain/frequence.py`, stdlib seule) à partir de ce JSON : aucune dépendance ajoutée à l'exécution, aucun pickle. La CI réentraîne quand le code du modèle ou les données changent, vérifie que l'artefact commité est reproduit et passe la porte ; le déploiement de staging en dépend.

**Tech Stack :** Python 3.12, scikit-learn (`PoissonRegressor`), pandas (groupe de dépendances `entrainement`, hors image), Azure Functions (zip, build distant), GitHub Actions.

**Spec :** `docs/superpowers/specs/2026-10-28-o7-glm-poisson-design.md` (issue #155). Branche `feat/glm-poisson` depuis `main`.

## Global Constraints

- Dépendances accordées le 28/10 : `scikit-learn` et `pandas`, **dernière version stable figée** (`==`), dans un groupe `entrainement` de `fonction-calcul` : `requirements.txt` de la Function **inchangé** (`make lint` compare `uv export --no-dev`). Aucune autre montée de version.
- Hexagonal : `domain/` n'importe que la stdlib (`tests/unit/test_architecture_calcul.py`) ; scikit-learn et pandas seulement sous `entrainement/`.
- Rôle : **comparaison seulement** — la fréquence n'entre jamais dans la décision, la prime ni le rapport de l'Actuaire ; `/api/evaluer` et `/api/calculer` inchangés (octet pour octet sur leurs tests).
- Variables : `BonusMalus` = `crm` × 100, `VehPower` = `puissance_fiscale_cv` (bornée au domaine de freMTPL2), `Region` = table département → ancienne région ; `DrivAge`, `VehAge`, `VehBrand`, `VehGas`, `Area`, `Density` **exclues** (écrit dans la fiche).
- Seuils jamais inventés : le modèle **bat le modèle nul** ; D² ≥ valeur **mesurée à la première exécution** moins une marge, notée avec sa mesure. Si le modèle ne bat pas le modèle nul : **arrêt et signalement** avant la Task 3.
- Données : freMTPL2 figé (URL, version, SHA-256, licence notés) ; jamais commité (cache CI) ; aucune donnée personnelle réelle ; corps de requête et profil jamais journalisés.
- Écritures Azure, Entra, `gh variable set` : à la main par Acerola. Gel des fusions du 29/10 au matin à la fin de la démo du 30/10. Français partout.

## Décisions du plan (constructeur, spec §8)

| Sujet | Décision |
|---|---|
| Format de l'artefact | JSON lisible (pas de pickle) : `{"version", "intercept", "bonus_malus": {"min", "max", "coef"}, "veh_power": {"min", "max", "coefs": {"4": …}}, "region": {"coefs": {"R11": …}}, "donnees": {"source", "version", "sha256", "licence"}, "metriques": {…}, "commit", "entraine_le"}` ; `BonusMalus` entre en `log` ; `VehPower` et `Region` en indicatrices (référence à 0). |
| Exposition | `PoissonRegressor` sur `y = ClaimNb / Exposure` avec `sample_weight = Exposure` : équivalent exact de l'offset `log(Exposure)` pour un GLM log-Poisson (écrit dans la fiche). |
| Préparation | `Exposure` plafonnée à 1, `ClaimNb` plafonné à 4, `BonusMalus` borné à [50, 230], `VehPower` à [4, 15] (modalités ≥ 12 regroupées) ; `Density` non utilisée (variable exclue). |
| Partage | 80 / 20, graine 42, `train_test_split` sur l'index ; test jamais vu par la préparation (bornes fixes, pas apprises). |
| Marge du seuil D² | D² du test mesuré − 0,005 (absolu), consigné dans `entrainement/seuils.toml` avec la mesure et la date. |
| Route | `POST /api/frequence` (Function) = `POST /api/calcul/frequence` par la gateway (route `calcul` existante, réécriture `/api/{**reste}`) : **aucun changement de gateway**, même politique `calcul-mcp`. |
| Hors domaine | Département sans région freMTPL2 (DOM : 971–976) ou champ absent → 422 `DONNEE_HORS_MODELE` avec le `champ` ; `crm` et puissance hors bornes du modèle → **bornés** (pas d'extrapolation), comme à l'entraînement. |
| Suivi en ligne | Ligne de journal `glm.frequence version=<v> frequence=<f arrondie à 4 décimales>` (aucune donnée du profil) ; appels et latence = requêtes App Insights de la Function. |

## Review Focus

1. Département d'outre-mer ou Corse (`2A`, `2B`) → DOM : 422 `DONNEE_HORS_MODELE` ; Corse : région `R94` → `test_frequence_dom_hors_modele`, `test_corse_en_r94` (Task 3).
2. `crm` = 3.50 (malus maximal, `BonusMalus` 350 > 230) et puissance 2 CV ou 40 CV → fréquence bornée, finie, sans exception → `test_bornes_sans_extrapolation` (Task 3).
3. Prédiction Python pur ≠ `PoissonRegressor.predict` (dérive entre l'entraînement et la Function) → `test_artefact_predit_comme_sklearn` (Task 2, écart ≤ 1e-9 sur 1 000 lignes).
4. Deux entraînements à graine fixée donnent des artefacts différents (CI non reproductible) → `test_entrainement_deterministe` (Task 2) et la comparaison de la Task 4.
5. Le barème et la prime changent par effet de bord → les tests existants de `test_routes_calcul.py`, `test_bareme.py`, `test_formule.py` restent verts sans modification (Task 3).

---

### Task 1 : Données freMTPL2 — téléchargement figé, préparation, partage (C12)

**Files :**
- Create : `fonction-calcul/entrainement/__init__.py`, `fonction-calcul/entrainement/donnees.py`, `fonction-calcul/entrainement/donnees.toml` (URL, version OpenML, SHA-256, licence)
- Modify : `fonction-calcul/pyproject.toml` (groupe `entrainement` : `scikit-learn==…`, `pandas==…`), `uv.lock`, `pyproject.toml` racine (`pythonpath` si nécessaire, marqueur `lent` déjà connu)
- Test : `fonction-calcul/tests/unit/test_donnees_glm.py`

**Interfaces :**
- Produces : `telecharger(cache: Path) -> Path` (vérifie le SHA-256, lève `ValueError` sinon) ; `charger(fichier: Path) -> pd.DataFrame` (colonnes `ClaimNb, Exposure, BonusMalus, VehPower, Region`) ; `preparer(df) -> pd.DataFrame` (bornes du tableau des décisions) ; `separer(df, graine: int = 42, part_test: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]`.

- [ ] **Step 1 : tests rouges.** Sur un petit DataFrame synthétique : `test_schema_et_bornes_apres_preparation` (Exposure ∈ ]0, 1], ClaimNb ∈ [0, 4], BonusMalus ∈ [50, 230], VehPower ∈ [4, 12], Region ∈ 22 codes) ; `test_separation_sans_fuite` (index disjoints, union = tout, 20 % ± 1 ligne) ; `test_separation_deterministe` (même graine → mêmes index) ; `test_sha_incorrect_refuse` (fichier modifié → `ValueError`). Marqué `lent` : `test_fremtpl2_reel_schema` (678 013 lignes attendues, à confirmer au téléchargement et figer dans `donnees.toml`).
- [ ] **Step 2 : constater l'échec.**
- [ ] **Step 3 : implémenter** ; trouver la source OpenML de freMTPL2freq (`data_id` 41214, à vérifier), noter URL, version, SHA-256 et licence dans `donnees.toml` ; `uv add --group entrainement` aux dernières versions stables, figées ; vérifier que le lock ne change aucune autre version.
- [ ] **Step 4 : `make test`, `make lint`** (requirements.txt de la Function inchangé), puis le test `lent` une fois.
- [ ] **Step 5 : commit** `feat(calcul): données freMTPL2 figées, préparation et partage testés (C12, #155)`.

### Task 2 : Entraînement, évaluation, artefact et fiche (C12)

**Files :**
- Create : `fonction-calcul/entrainement/modele.py`, `fonction-calcul/entrainement/__main__.py` (`python -m entrainement`), `fonction-calcul/entrainement/seuils.toml`
- Create (sortie commitée) : `fonction-calcul/agentinsurflow_calcul/modeles/glm-freq-<AAAAMMJJ>-v1.json`, `fonction-calcul/agentinsurflow_calcul/modeles/glm-freq-<AAAAMMJJ>-v1.md` (fiche)
- Modify : `Makefile` (cible `modele` : entraîne, évalue, écrit l'artefact, la fiche et `rapport-modele.md` non commité)
- Test : `fonction-calcul/tests/unit/test_modele_glm.py`

**Interfaces :**
- Consumes : Task 1 (`charger`, `preparer`, `separer`).
- Produces : `entrainer(train: pd.DataFrame) -> PoissonRegressor` ; `evaluer(modele, test) -> dict` avec `deviance_moyenne`, `deviance_moyenne_nul`, `d2`, `gini`, `calibration` (10 déciles : prédite, observée) ; `exporter(modele, metriques, donnees, version: str) -> dict` (schéma JSON du tableau des décisions) ; `porte(metriques, seuils) -> list[str]` (raisons d'échec, vide si OK).

- [ ] **Step 1 : tests rouges** (données synthétiques avec effet connu de `BonusMalus`) : `test_bat_le_modele_nul` ; `test_entrainement_deterministe` (deux artefacts identiques à la graine) ; `test_converge` (`n_iter_ < max_iter`, aucun `ConvergenceWarning`) ; `test_artefact_predit_comme_sklearn` (1 000 lignes, écart ≤ 1e-9, via une fonction de prédiction lue dans le JSON, la même que la Task 3 reprendra) ; `test_porte_refuse_sous_le_seuil` ; `test_calibration_dix_deciles`.
- [ ] **Step 2 : constater l'échec.**
- [ ] **Step 3 : implémenter** ; `PoissonRegressor(alpha=…)` choisi et noté dans la fiche ; Gini par la courbe de Lorenz pondérée par l'exposition.
- [ ] **Step 4 : première exécution réelle** `make modele` : **si D² ≤ 0 ou déviance ≥ modèle nul, arrêter et signaler (BLOCKED)**. Sinon écrire `seuils.toml` (`d2_min = d2_mesure − 0.005`, mesure, date) et commiter l'artefact et la fiche (variables exclues, source, licence, exposition en équivalent offset, métriques test et modèle nul, calibration, commit, limites).
- [ ] **Step 5 : `make test`, `make lint`.** Commit `feat(calcul): GLM Poisson de fréquence entraîné, évalué, porte de qualité (C12, #155)`.

### Task 3 : Prédiction dans la Function — domaine et route `/api/frequence`

**Files :**
- Create : `fonction-calcul/agentinsurflow_calcul/domain/frequence.py`, `fonction-calcul/agentinsurflow_calcul/domain/regions.py` (département → ancienne région freMTPL2)
- Modify : `fonction-calcul/function_app.py` (route `frequence`, `/api/sante` porte `modele_frequence`), `fonction-calcul/README.md`
- Test : `fonction-calcul/tests/unit/test_frequence.py`, `fonction-calcul/tests/unit/test_routes_calcul.py` (ajouts seulement)

**Interfaces :**
- Consumes : l'artefact JSON de la Task 2 (chemin lu par `importlib.resources` dans `agentinsurflow_calcul/modeles/`, le plus récent par nom).
- Produces : `ProfilFrequence(crm: Decimal | None, puissance_fiscale_cv: int | None, departement: str | None)` ; `PredictionFrequence(version_modele: str, frequence_annuelle: float)` ; `charger_modele() -> ModeleFrequence` ; `predire(modele, profil) -> PredictionFrequence` (lève `DonneeHorsModele(champ)`). Réponse HTTP : `{"version_modele", "frequence_annuelle", "variables": ["BonusMalus", "VehPower", "Region"]}` ; 400 `REQUETE_INVALIDE` (corps strict, comme `/api/evaluer`) ; 422 `DONNEE_HORS_MODELE` avec `champ`.

- [ ] **Step 1 : tests rouges** : `test_frequence_dom_hors_modele` ; `test_corse_en_r94` ; `test_tous_les_departements_metropolitains_ont_une_region` (les 96 de `formule._DEPARTEMENTS` hors DOM) ; `test_bornes_sans_extrapolation` (`crm` 3.50, 2 CV, 40 CV) ; `test_predire_egale_la_task_2` (même valeur que la fonction de prédiction testée contre sklearn) ; route : `test_frequence_200`, `test_frequence_corps_invalide_400`, `test_frequence_journal_sans_profil` (le journal ne contient ni `crm` ni département) ; `test_architecture_calcul.py` reste vert.
- [ ] **Step 2 : constater l'échec.**
- [ ] **Step 3 : implémenter** (stdlib seule dans `domain/`) ; la fonction de prédiction de la Task 2 est **remplacée** par `domain.frequence.predire` (une seule implémentation, utilisée par les tests de la Task 2).
- [ ] **Step 4 : `make test`, `make lint`** ; tests du barème et de la prime inchangés et verts.
- [ ] **Step 5 : commit** `feat(calcul): fréquence prédite par le GLM, à côté du barème (#155)`.

### Task 4 : Livraison continue du modèle (C13)

**Files :**
- Modify : `.github/workflows/ci-cd.yml` (job `modele`), `.github/workflows/deploy.yml` (fumée : `POST $URL/api/calcul/frequence` sans jeton → 401 par la gateway)
- Test : `tests/unit/test_ci_modele.py` (racine, lit les workflows)

- [ ] **Step 1 : tests rouges** : `test_job_modele_filtre_ses_chemins` (`fonction-calcul/entrainement/**`, `domain/frequence.py`, `domain/regions.py`, `modeles/**`, `donnees.toml`) ; `test_staging_attend_la_porte_du_modele` (`staging` a `modele` dans `needs` et ne part pas si `modele` a échoué ; sauté = autorisé) ; `test_donnees_en_cache_par_sha` (`actions/cache` clé contenant le SHA de `donnees.toml`) ; `test_rapport_joint_au_run` (`actions/upload-artifact` du rapport) ; `test_fumee_frequence_fermee_sans_jeton`.
- [ ] **Step 2 : constater l'échec.**
- [ ] **Step 3 : implémenter** le job : filtre de chemins (même technique que `changements`) → cache des données → tests C12 (dont `lent`) → `make modele` → **l'artefact réentraîné est identique à l'artefact commité** (sinon échec : commiter le nouvel artefact) → porte `seuils.toml` → rapport en artefact du run. Pas de nouveau secret ni de variable.
- [ ] **Step 4 : `make test`, `make lint`**, `actionlint` si présent.
- [ ] **Step 5 : commit** `ci(calcul): le modèle n'est déployé que si sa porte passe (C13, #155)`.

### Task 5 : Vigie et dossier

**Files :**
- Create : `infra/vigie/kql/tuiles/frequence-glm.kql` (appels, latence p95 de `frequence`, distribution des fréquences depuis `glm.frequence`), `docs/dossier/amendements-d42.md` (D42 : V2 → sprint 5 ; section · texte actuel · texte corrigé, cité du PDF `Brief5/dossier-conception-v1.2.pdf`, sinon « à vérifier dans le PDF »)
- Modify : `docs/contrat-personnel.md` (C12/C13 : preuves), `fonction-calcul/README.md`

- [ ] **Step 1 : écrire** ; la tuile dans `infra/vigie/dashboard.json` n'est ajoutée qu'**après la fusion de #162** (S2) : si `infra/vigie/dashboard.json` n'existe pas sur la branche, consigner la tuile comme suite dans la PR (fichier KQL prêt, gabarits `$APPI_ID` comme ceux de S2).
- [ ] **Step 2 : `make test`, `make lint`.** Commit `docs(calcul): fiche, tuile KQL et amendement D42 (#155)`.

### Task 6 : manuel (Acerola)

- [ ] Relire la fiche et le seuil D² mesuré.
- [ ] Fusion hors gel ; le job `modele` et la fumée passent en CI ; staging déployé.
- [ ] Appel authentifié `POST /api/calcul/frequence` par la gateway en staging (jeton portant le rôle `Calcul`, audience calcul : celui du serveur MCP ; voir la question ouverte ci-dessous).
- [ ] Après la fusion de #162 : ajouter la tuile au tableau de bord (`make vigie`).

**Question ouverte (à trancher par Acerola)** : la route `calcul` de la gateway n'accepte que le rôle `Calcul` (le serveur MCP). La preuve « un appel passe par la gateway » (spec §7.3) se fait donc avec un jeton du MCP, ou par un nouvel outil MCP de comparaison ; ouvrir la route au rôle `Gestionnaire` changerait la politique et n'est pas prévu ici.
