# O2 + O3 — Tableau de bord et alertes : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `make vigie ENV=…` pose aussi, en plus de l'étape App Insights de S1, l'Action Group e-mail, les règles d'alerte AL-1 → AL-9, le test de disponibilité et le tableau de bord. Les requêtes KQL sont versionnées et servent de source unique.

**Architecture:** Les requêtes vivent dans `infra/vigie/kql/`, une par fichier. Chacune renvoie une colonne `valeur`, et les placeholders `$APPI_ID`, `$CLUSTER_APP` et `$PRIX_KQL` sont substitués au lancement par `envsubst`. Le catalogue des règles (fréquence, fenêtre, opérateur, seuil, gravité) est dans `infra/vigie/alertes.tsv`. `infra/vigie.sh` le parcourt et appelle `az` à travers `${AZ:-az}`, ce qui permet de le tester sans Azure grâce à un faux `az`. Le tableau de bord est un modèle `infra/vigie/dashboard.json` complété par `jq`.

**Tech Stack:** bash, Azure CLI (`monitor action-group`, `monitor scheduled-query`, `monitor app-insights web-test`, extension `portal`), `jq`, `envsubst`, KQL (tables `AppTraces`, `AppRequests`, `AppDependencies`, `ContainerAppSystemLogs_CL`), pytest (racine `tests/unit`).

**Spec:** `docs/superpowers/specs/2026-10-28-o2-o3-dashboard-alertes-design.md`. S'appuie sur S1 (`docs/superpowers/plans/2026-10-28-o1-instrumentation-app-insights.md`, PR #158).

## Global Constraints

- Écritures Azure **seulement** par `make vigie`, lancé **à la main par Acerola**. Un agent ne lance jamais `vigie.sh` (sauf avec un ENV invalide ou un faux `AZ`), ni aucun `az … create/update/set`.
- **Aucun seuil inventé.** AL-8 et AL-9 restent `🔴`. Le dossier de conception v1.2, L7.5 (p. 33), dit seulement « A5 : 429 Azure OpenAI » et « A11 : 403 gateway après déploiement », sans valeur chiffrée. Leurs règles ne sont créées que si `SEUIL_AL8` ou `SEUIL_AL9` est posé dans `.env`.
- **Aucune conversion de devise.** AL-6 est en USD. Les prix par modèle viennent de `.env` (`PRIX_USD_MILLION`, aucune valeur dans le dépôt). Sans prix, AL-6 n'est pas créée.
- Une seule source par requête : le tableau de bord et les alertes lisent les mêmes fichiers `infra/vigie/kql/*.kql`.
- Les requêtes App Insights filtrent par `_ResourceId =~ "$APPI_ID"` (un seul workspace pour les deux environnements, D-V1). AL-3 filtre par `ContainerAppName_s == "$CLUSTER_APP"`.
- Destinataire des e-mails : `ALERTE_EMAIL` (`.env`, valeur décidée en D-V5b, jamais écrite dans le dépôt). `.env.example` reste sans valeurs.
- Les alertes existent dans les deux environnements, avec les mêmes seuils (spec §5).
- Gel des fusions sur `main` du 29/10 au matin à la fin de la démo du 30/10. La branche `feat/vigie-s2` part de S1 et sera rebasée sur `main` après la fusion de la #158.
- Français partout. Pas de changement de version.

## Review Focus

- **`.env` incomplet** (`ALERTE_EMAIL`, `PRIX_USD_MILLION`, `SEUIL_AL8` ou `SEUIL_AL9` absents) : le script ne doit pas créer de règle à moitié configurée. `ALERTE_EMAIL` absent arrête le script ; un prix ou un seuil absent saute seulement la règle concernée, en le disant (test Task 2).
- **Second lancement** : tout est un PUT ARM, rien n'est dupliqué. Les noms sont stables (`ag-insurflow-<env>`, `al-<n>-<env>`, `web-sante-<env>`, `vigie-<env>`). Le test Task 2 vérifie que les noms ne dépendent que de l'ENV.
- **Volume faible** (moins de 10 évaluations) : AL-5 et AL-7 ne doivent pas se déclencher. Leur `valeur` est nulle sous le volume minimal (test Task 1 sur le texte de la requête).
- **Fenêtre de requête tronquée** : AL-7 compare la dernière heure à la moyenne sur 7 jours. Si la fenêtre de la règle limite la plage interrogée, la moyenne est fausse. Voir la Task 4, étape 2.
- **Texte de l'e-mail** : il doit contenir le nom de l'alerte, l'environnement et le lien vers l'ancre de `docs/exploitation.md` (test Task 2).

---

### Task 1 : requêtes KQL et catalogue des règles

**Files:**
- Create : `infra/vigie/kql/al-1-latence-p95.kql`, `al-2-llm-ko.kql`, `al-3-garde-fous-chargement.kql`, `al-4-mcp-indisponible.kql`, `al-5-revue-humaine.kql`, `al-6-cout-dossier.kql`, `al-7-refus-garde-fous.kql`, `al-8-foundry-429.kql`, `al-9-gateway-403.kql`
- Create : `infra/vigie/kql/tuiles/evaluations-par-heure.kql`, `revue-par-cause.kql`, `cout-par-agent.kql`, `sans-decision.kql`
- Create : `infra/vigie/alertes.tsv`
- Test : `tests/unit/test_vigie_kql.py`

**Interfaces:**
- Produces : chaque fichier `al-*.kql` renvoie **une ligne et une colonne numérique `valeur`**, calculée sur toute la plage interrogée. La plage est la fenêtre de la règle, ou la période du tableau de bord.
- Produces : `alertes.tsv`, séparé par des tabulations, avec l'en-tête `id	kql	frequence	fenetre	operateur	seuil	gravite	ancre`. `seuil` vaut un nombre, ou `env:SEUIL_AL8` / `env:SEUIL_AL9`. `ancre` est l'ancre de `docs/exploitation.md` que S3 rédigera (`al-1` → `al-9`).

Sources des données (S1) :
- `AppTraces`, `Message == "audit.evaluation"`, avec `Properties.duree_ms`, `statut_final` et `cause` ;
- `Message == "audit.agent"`, avec `Properties.cause` (`llm_ko`), `modele`, `tokens_entree`, `tokens_sortie` ;
- la cause `MCP_INDISPONIBLE` vient de `ErreurOutil("MCP_INDISPONIBLE", …)` (`infrastructure/mcp/client.py`), reprise dans `audit.evaluation.cause` ;
- les 429 de Foundry sont des `AppDependencies` de la gateway avec `ResultCode == "429"` ;
- les 403 sont des `AppRequests` de la gateway avec `ResultCode == "403"`.

- [ ] **Step 1 : test du catalogue (il doit échouer)**

```python
LIGNES = {  # id: (kql, frequence, fenetre, operateur, seuil, gravite) — spec §4 et §5
    "AL-1": ("al-1-latence-p95.kql", "15m", "15m", ">", "30000", "2"),
    "AL-2": ("al-2-llm-ko.kql", "5m", "5m", ">=", "1", "1"),
    "AL-3": ("al-3-garde-fous-chargement.kql", "5m", "5m", ">", "180", "1"),
    "AL-4": ("al-4-mcp-indisponible.kql", "5m", "5m", ">=", "1", "1"),
    "AL-5": ("al-5-revue-humaine.kql", "1h", "2h", ">", "30", "2"),
    "AL-6": ("al-6-cout-dossier.kql", "1h", "1d", ">", "0.15", "2"),
    "AL-7": ("al-7-refus-garde-fous.kql", "1h", "1h", ">", "2", "2"),
    "AL-8": ("al-8-foundry-429.kql", "1h", "1h", ">=", "env:SEUIL_AL8", "2"),
    "AL-9": ("al-9-gateway-403.kql", "1h", "1h", ">=", "env:SEUIL_AL9", "2"),
}


def test_catalogue_fidele_a_la_spec(): ...  # chaque ligne de alertes.tsv == LIGNES[id] + ancre == id.lower()
def test_chaque_requete_existe_et_produit_valeur(): ...  # fichier présent, contient "valeur"
def test_filtre_par_ressource(): ...  # "$APPI_ID" dans tout al-*.kql et tuiles/*.kql sauf al-3 ; "$CLUSTER_APP" dans al-3
def test_volume_minimal_al5_al7(): ...  # "10" et "iff(" dans al-5 et al-7 (valeur nulle sous 10 évaluations)
def test_cout_sans_prix_en_dur(): ...  # "$PRIX_KQL" dans al-6 et cout-par-agent ; aucun nombre décimal de prix
```

- [ ] **Step 2 : lancer, constater l'échec** avec `uv run pytest tests/unit/test_vigie_kql.py -v`.
- [ ] **Step 3 : écrire les 13 requêtes et `alertes.tsv`.**
  - **AL-1** : p95 de `duree_ms`.
  - **AL-2** : nombre d'`audit.agent` avec `cause == "llm_ko"`.
  - **AL-3** : écart en secondes entre le premier et le dernier `Reason_s == "ProbeFailed"` de `$CLUSTER_APP` dans `ContainerAppSystemLogs_CL`.
  - **AL-4** : nombre d'`audit.evaluation` avec `cause == "MCP_INDISPONIBLE"`.
  - **AL-5** : pourcentage de `statut_final == "REVUE_HUMAINE"`, nul si moins de 10 évaluations.
  - **AL-6** : $ moyen par dossier, soit Σ des jetons × prix (via `let prix = datatable(modele:string, entree:real, sortie:real)[$PRIX_KQL];`, prix par million) divisé par le nombre d'`audit.evaluation`.
  - **AL-7** : taux de `cause startswith "garde_fou:"` sur `ago(1h)`, divisé par le taux sur `ago(7d)`, nul si moins de 10 évaluations dans l'heure.
  - **AL-8 et AL-9** : nombre de 429 et de 403.
  - **Tuiles** : nombre par `bin(TimeGenerated, 1h)`, répartition de `REVUE_HUMAINE` par `cause`, coût par agent et par modèle, pourcentage de `statut_final == "ERREUR"`.
- [ ] **Step 4 : relancer, constater le succès**, puis `make test`.
- [ ] **Step 5 : commit** `feat(vigie): requêtes KQL et catalogue des alertes AL-1 → AL-9 (S2)`.

### Task 2 : `infra/vigie.sh`, Action Group, règles et test de disponibilité

**Files:**
- Modify : `infra/vigie.sh` (après l'étape ③ de S1 ; l'ancien récapitulatif ④ devient la dernière étape)
- Modify : `.env.example` (ajouter `ALERTE_EMAIL=`, `PRIX_USD_MILLION=`, `SEUIL_AL8=`, `SEUIL_AL9=`, sans valeurs, avec un commentaire d'une ligne chacune ; format `PRIX_USD_MILLION="<modele>=<entree>/<sortie>;…"`, USD par million de jetons, valeurs Global de D-V15)
- Test : `tests/unit/test_vigie.py` (étendre) et `tests/unit/faux_az.sh` (nouveau)

**Interfaces:**
- Consumes : `alertes.tsv` et `kql/` (Task 1).
- Produces : ressources nommées `ag-insurflow-$env`, `al-<n>-$env` (n = 1…9), `web-sante-$env`. Le script expose `APPI_ID`, `WORKSPACE_ID`, `AG_ID` et `GATEWAY_FQDN` à la Task 3 (même script).

- [ ] **Step 1 : tests (ils doivent échouer).** `faux_az.sh` journalise ses arguments, un appel par ligne, dans `$FAUX_AZ_JOURNAL`. Pour les `show … --query …`, il répond une valeur factice (`/subscriptions/x/…`, `chaine-factice`, `gw.exemple`). Les tests lancent `bash infra/vigie.sh staging` avec `AZ=tests/unit/faux_az.sh` et les variables minimales du `.env`, passées dans `env=` de `subprocess.run`.

```python
def test_sans_alerte_email_le_script_s_arrete(): ...  # returncode != 0, "ALERTE_EMAIL" dans la sortie
def test_une_regle_par_ligne_du_catalogue(): ...  # avec PRIX et SEUIL_AL8/9 posés : 9 "scheduled-query create", noms al-1-staging … al-9-staging
def test_sans_prix_ni_seuils_trois_regles_sautees(): ...  # 6 règles créées ; sortie cite AL-6, AL-8, AL-9 « non créée »
def test_description_cite_alerte_env_et_ancre(): ...  # chaque create : --description contient "AL-n", "staging", "docs/exploitation.md#al-n"
def test_noms_stables_entre_deux_lancements(): ...  # journal du 1er lancement == journal du 2e
def test_chaine_jamais_affichee(): ...  # "chaine-factice" absent de stdout+stderr
```

- [ ] **Step 2 : lancer, constater l'échec.**
- [ ] **Step 3 : implémenter.**
  - Remplacer chaque appel `az` par `"${AZ:-az}"`.
  - Contrôler `ALERTE_EMAIL` avant la première écriture.
  - **④ Action Group** : `monitor action-group create -n ag-insurflow-$env --short-name insurflow --action email vigie "$ALERTE_EMAIL"`.
  - **⑤ Règles** : boucle `while IFS=$'\t' read` sur `alertes.tsv`.
    - La requête passe par `envsubst '$APPI_ID $CLUSTER_APP $PRIX_KQL'`, avec `$PRIX_KQL` construit à partir de `PRIX_USD_MILLION` (`"m",e,s,` par modèle).
    - Appel : `monitor scheduled-query create -n al-<n>-$env --scopes "$WORKSPACE_ID" --condition "max 'valeur' from 'Q' <op> <seuil>" --condition-query Q=… --evaluation-frequency … --window-size … --severity … --action-groups "$AG_ID" --auto-mitigate true --description "AL-n (<env>) : <signal> — https://github.com/acerolaz/agentinsurflow/blob/main/docs/exploitation.md#al-n"`.
    - La règle est sautée, avec un message, si `env:SEUIL_*` est vide (AL-8, AL-9) ou si `PRIX_USD_MILLION` est vide (AL-6).
  - **⑥ Test de disponibilité standard** : `monitor app-insights web-test create -n web-sante-$env --kind standard --request-url "https://$GATEWAY_FQDN/health" --frequency 300`, avec les emplacements par défaut et le tag `hidden-link` vers `$APPI_ID`.
  - Lancer `shellcheck infra/vigie.sh`.
- [ ] **Step 4 : relancer, constater le succès**, puis `make test` et `make lint`.
- [ ] **Step 5 : commit** `feat(vigie): Action Group, règles AL-1 → AL-9 et test de disponibilité (S2)`.

### Task 3 : tableau de bord

**Files:**
- Create : `infra/vigie/dashboard.json` (modèle)
- Modify : `infra/vigie.sh` (étape ⑦ : `portal dashboard create -n vigie-$env --input-path <fichier assemblé>`, avec l'extension `portal`)
- Test : `tests/unit/test_vigie_tableau.py`

**Interfaces:**
- Consumes : `kql/` (Task 1) et les variables de la Task 2.
- Produces : un tableau de bord `vigie-$env` par environnement.

Les **tuiles** sont celles de la spec §6, et leur titre est la question. Le modèle contient :
- une tuile Markdown « Comment lire ce tableau » ;
- une tuile par question, de type `LogsDashboardPart` sur `$WORKSPACE_ID`, dont la requête vaut `"@kql:<fichier>"` ;
- une tuile de disponibilité pour `web-sante-$env`.

Le script remplace chaque `"@kql:<fichier>"` par le texte substitué du fichier (`jq --rawfile`), puis les `$…` des identifiants.

L'**objectif** est écrit dans le titre ou le sous-titre de la tuile (par exemple « Combien de temps prend une évaluation ? — objectif ≤ 30 s »), jamais porté par la seule couleur. La période par défaut est de 24 h, avec actualisation automatique.

- [ ] **Step 1 : tests (ils doivent échouer).**

```python
QUESTIONS = [
    "Comment lire ce tableau",
    "Le service répond-il ?",
    "Combien de dossiers évalués ?",
    "Combien de temps prend une évaluation ?",
    "Quelle part part en revue humaine, et pourquoi ?",
    "Combien coûte un dossier ?",
    "Les garde-fous bloquent-ils plus que d'habitude ?",
    "Combien d'évaluations sans décision ?",
    "Le modèle de langage est-il disponible ?",
    "Alertes en cours",
]


def test_une_tuile_par_question(): ...  # chaque question apparaît dans un titre de tuile du modèle
def test_objectif_ecrit_sur_les_tuiles(): ...  # "30 s", "20 %", "0,15", "1 %", "100 %" présents dans les titres ou sous-titres
def test_requetes_viennent_des_fichiers(): ...  # chaque "@kql:x" référence un fichier existant de infra/vigie/kql
def test_assemblage_sans_placeholder(): ...  # vigie.sh avec faux az : le JSON passé à "portal dashboard create" est valide et ne contient ni "@kql:" ni "$APPI_ID"
```

- [ ] **Step 2 : lancer, constater l'échec.**
- [ ] **Step 3 : écrire le modèle et l'étape ⑦.** Le schéma des tuiles et la mise en page sont libres (spec §9).
- [ ] **Step 4 : relancer, constater le succès**, puis `make test`.
- [ ] **Step 5 : commit** `feat(vigie): tableau de bord par environnement, une tuile par question (S2)`.

### Task 4 : catalogue dans la doc

**Files:**
- Modify : `docs/contrat-personnel.md` §4 (une ligne par AL-n : signal, seuil, argument, requête = lien vers le fichier `infra/vigie/kql/…`, alerte, action = ancre `docs/exploitation.md#al-n` ; marquer « requête à valider en staging » jusqu'à la Task 5)
- Modify : `docs/superpowers/specs/2026-10-28-o2-o3-dashboard-alertes-design.md` (§4 : AL-8, AL-9 et SLO-4 avec le constat L7.5 p. 33 ; §5 : AL-8 et AL-9 non créées sans `SEUIL_*`, au lieu de « créée désactivée », car une règle désactivée exigerait quand même un seuil)

- [ ] **Step 1 : écrire les deux changements.** Une phrase par fait, chaque fait sourcé. Aucun seuil autre que ceux du §4.
- [ ] **Step 2 : risque sur AL-7, à écrire.** Ajouter à la ligne AL-7 : « si la fenêtre de 1 h limite la plage interrogée, porter la fenêtre au maximum autorisé et consigner la moyenne réellement calculée ». Ce sera vérifié à la Task 5.
- [ ] **Step 3 : vérifier** avec `uv run pytest tests/unit -q` et `make lint`.
- [ ] **Step 4 : commit** `docs(vigie): catalogue AL-1 → AL-9 dans le contrat personnel (S2)`.

### Task 5 (manuelle, Acerola) : lancement et preuves

Hors exécution d'un agent : écritures Azure et e-mails réels. C'est la spec §7.

- [ ] `.env` : `ALERTE_EMAIL`, puis `PRIX_USD_MILLION`, lu sur la page de tarifs Azure (Global, USD), pour chaque `modele` vu dans `audit.agent`.
- [ ] `make vigie ENV=staging`, puis une deuxième fois : aucune différence (idempotence).
- [ ] Chaque fichier `infra/vigie/kql/*.kql` est exécuté dans le workspace avec `$APPI_ID` substitué. Résultat noté non vide, ou vide avec une explication. Si AL-3 ne trouve pas `ContainerAppSystemLogs_CL`, utiliser la table réellement présente et corriger le fichier. Pour AL-7, vérifier la troncature.
- [ ] **Dérive simulée** : `make recette ACTION=llm-off`, une évaluation, réception de l'e-mail AL-2, puis `make recette ACTION=llm-on` et réception de l'e-mail de résolution. Heures et capture consignées dans `eval/preuves/alerte-<date>-staging.md`.
- [ ] **Test de lecture** : les 5 questions de la spec §7.3, posées à une personne non développeuse, réponses consignées.
- [ ] `make vigie ENV=production`. `docs/contrat-personnel.md` : retirer « à valider ».
