# Calcul du risque et de la prime — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Débloquer `evaluer_risque` et `calculer_prime` (T9, #64) : barème et formule en fonctions pures dans une Azure Function Python, appelée directement par le serveur MCP, sur des faits lus dans la vue minimisée étendue d'underwriting-admin.

**Architecture:** `fonction-calcul/` = domaine pur (`bareme.py`, `formule.py`) + adaptateur HTTP Azure Functions (`function_app.py`), sans état ni I/O. underwriting-admin ajoute six colonnes à `vue_contrat_minimisee` et à `VueContrat`. Le serveur MCP lit le contrat en OBO par la gateway, extrait les faits (fonction pure du domaine), appelle la Function par un `CalculateurPort` (adaptateur httpx, jeton de l'identité managée en Azure).

**Tech Stack:** Python 3.12, `azure-functions` (modèle v2), uv workspace, pytest ; .NET 10, EF Core (migrations SQL), xUnit ; GitHub Actions + az CLI.

**Spec:** [`docs/superpowers/specs/2026-10-22-calcul-risque-prime-design.md`](../specs/2026-10-22-calcul-risque-prime-design.md) (complète [`2026-10-21-serveur-mcp-design.md`](../specs/2026-10-21-serveur-mcp-design.md) § 5.3).

## Global Constraints

- Branche `feat/RiskPrime` (partie de `feat/mcp`), PR en brouillon ; jamais de push sur `main`.
- Dépendances **validées par Acerola le 22/10** : `azure-functions` (dernière version stable, épinglée `==` dans `fonction-calcul/pyproject.toml` comme `mcp==1.30.0`) et l'image `mcr.microsoft.com/azure-functions/python:4-python3.12`. Aucune autre dépendance ni changement de version.
- Versions : `bareme-2026.10-v1`, `formule-2026.10-v1`.
- Date de référence = date d'effet du contrat ; jamais la date du jour.
- Aucun coefficient ni règle par défaut : donnée absente (`null`) ou inconnue → `DONNEE_HORS_BAREME` (422) ; requête malformée → `REQUETE_INVALIDE` (400) → `CALCUL_INDISPONIBLE` côté MCP.
- `Decimal` partout dans la formule, `ROUND_HALF_UP` au centime à la fin seulement ; montants en chaînes dans le JSON.
- Jamais dans une trace ou un log : faits, classe, score, règles, montants, `numero_contrat`, jeton, corps de requête ou de réponse.
- Aucun secret : `.env.example` sans valeur ; scripts `infra/*.sh` rédigés, **lancés à la main par Acerola**.
- Tests selon `.claude/rules/testing-pyramid.md` (couverture ≥ 80 %) ; test d'architecture des imports pour `fonction-calcul`.
- Noms JSON et colonnes **sans chiffre** (`JsonNamingPolicy.SnakeCaseLower` de .NET ne sépare pas les chiffres : `NbSinistres36m` → `nb_sinistres36m`) : `nb_sinistres_trois_ans`, `nb_sinistres_responsables_trois_ans`.

## Review Focus

1. **Bornes exactes** (CRM 1,25 accepté / 1,26 refusé ; 2 / 3 responsables ; 4 / 5 sinistres ; permis 35 / 36 mois ; 7 / 8 CV) — tests paramétrés en tâche 1.
2. **Valeur JSON `null` vs clé absente** : `null` = donnée absente (422), clé absente ou mauvais type (dont un booléen pour un entier, un nombre pour `crm`) = requête malformée (400) — tests en tâche 3.
3. **Demi-centime** : un HT qui tombe sur ,xx5 s'arrondit vers le haut (pas d'arrondi bancaire) — test en tâche 2.
4. **Contrat sans véhicule** : `puissance_fiscale_cv` et `type_usage` à `NULL` dans la vue → `DONNEE_HORS_BAREME` côté MCP, jamais une acceptation — tests en tâches 4 (vue) et 5 (faits `None` transmis tels quels).
5. **Function injoignable ou lente** (démarrage à froid) : délai de 10 s puis `CALCUL_INDISPONIBLE`, sans données dans le span — test en tâche 5.

---

### Task 1: Barème `evaluer_risque` (domaine pur de la Function)

**Files:**
- Create: `fonction-calcul/pyproject.toml`, `fonction-calcul/agentinsurflow_calcul/__init__.py`, `fonction-calcul/agentinsurflow_calcul/domain/__init__.py`, `fonction-calcul/agentinsurflow_calcul/domain/models.py`, `fonction-calcul/agentinsurflow_calcul/domain/bareme.py`
- Modify: `pyproject.toml` (racine : `[tool.uv.workspace] members`, `[tool.uv.sources]`, `dependencies`, `testpaths`, `pythonpath`, `addopts --cov=agentinsurflow_calcul`), `Makefile` (cible `test` : ajouter `fonction-calcul/tests/unit`), `uv.lock`
- Test: `fonction-calcul/tests/unit/test_bareme.py`

**Interfaces:**
- Produces (`domain/models.py`, dataclasses `frozen=True`, stdlib seulement) :
  - `FaitsRisque(suspensions: int | None, resiliations: int | None, crm: Decimal | None, nb_sinistres_responsables_trois_ans: int | None, nb_sinistres_trois_ans: int | None, anciennete_permis_mois: int | None, puissance_fiscale_cv: int | None)`
  - `RegleDeclenchee(regle_id: str, motif: str)`
  - `ResultatRisque(version_bareme: str, classe: Literal["acceptable", "refus"], decision: Literal["ACCEPTE", "REFUSE"], score: float, regles: tuple[RegleDeclenchee, ...])`
  - `class DonneeHorsBareme(Exception)` avec l'attribut `champ: str` (nom du champ, jamais sa valeur)
- Produces (`domain/bareme.py`) : `VERSION_BAREME = "bareme-2026.10-v1"`, `evaluer(faits: FaitsRisque) -> ResultatRisque`

- [ ] **Step 1: Créer le paquet** `agentinsurflow-calcul` (version `0.1.0`, `requires-python = ">=3.12,<3.13"`, `dependencies = ["azure-functions==<dernière stable>"]`, hatchling, `packages = ["agentinsurflow_calcul"]`, calqué sur `serveur-mcp/pyproject.toml`) ; l'ajouter au workspace racine ; `uv lock`.

- [ ] **Step 2: Écrire les tests qui échouent** — `test_bareme.py`, avec un constructeur `faits(**surcharges)` dont le défaut est le seed 1 (`suspensions=0, resiliations=0, crm=Decimal("0.90"), nb_sinistres_responsables_trois_ans=0, nb_sinistres_trois_ans=0, anciennete_permis_mois=91, puissance_fiscale_cv=5`) :

```python
def test_seed_1_accepte_score_0():
    r = evaluer(faits())
    assert (r.version_bareme, r.classe, r.decision, r.score, r.regles) == (
        "bareme-2026.10-v1",
        "acceptable",
        "ACCEPTE",
        0.0,
        (),
    )


def test_seed_4_refuse_par_la_suspension_seule():  # CRM 1,25 et 2 responsables ne déclenchent pas
    r = evaluer(
        faits(
            suspensions=1,
            crm=Decimal("1.25"),
            nb_sinistres_responsables_trois_ans=2,
            nb_sinistres_trois_ans=2,
            anciennete_permis_mois=70,
        )
    )
    assert [x.regle_id for x in r.regles] == ["R01_SUSPENSION"]
    assert (r.classe, r.decision, r.score) == ("refus", "REFUSE", 1.0)


def test_seed_6_refuse_par_deux_resiliations():
    assert [x.regle_id for x in evaluer(faits(resiliations=2)).regles] == ["R02_RESILIATIONS"]


def test_une_resiliation_ne_suffit_pas():  # seed 2
    assert (
        evaluer(
            faits(resiliations=1, nb_sinistres_trois_ans=1, nb_sinistres_responsables_trois_ans=1)
        ).decision
        == "ACCEPTE"
    )


@pytest.mark.parametrize(
    "surcharge, regle, declenchee",
    [
        ({"crm": Decimal("1.25")}, "R03_CRM", False),
        ({"crm": Decimal("1.26")}, "R03_CRM", True),
        (
            {"nb_sinistres_responsables_trois_ans": 2, "nb_sinistres_trois_ans": 2},
            "R04_SINISTRES_RESPONSABLES",
            False,
        ),
        (
            {"nb_sinistres_responsables_trois_ans": 3, "nb_sinistres_trois_ans": 3},
            "R04_SINISTRES_RESPONSABLES",
            True,
        ),
        ({"nb_sinistres_trois_ans": 4}, "R05_SINISTRES_TOTAL", False),
        ({"nb_sinistres_trois_ans": 5}, "R05_SINISTRES_TOTAL", True),
        (
            {"anciennete_permis_mois": 35, "puissance_fiscale_cv": 7},
            "R06_JEUNE_PERMIS_PUISSANCE",
            False,
        ),
        (
            {"anciennete_permis_mois": 35, "puissance_fiscale_cv": 8},
            "R06_JEUNE_PERMIS_PUISSANCE",
            True,
        ),
        (
            {"anciennete_permis_mois": 36, "puissance_fiscale_cv": 8},
            "R06_JEUNE_PERMIS_PUISSANCE",
            False,
        ),
    ],
)
def test_bornes(surcharge, regle, declenchee): ...  # regle in ids == declenchee


def test_toutes_les_regles_declenchees_dans_l_ordre():
    r = evaluer(
        faits(
            suspensions=1,
            resiliations=2,
            crm=Decimal("1.5"),
            nb_sinistres_responsables_trois_ans=3,
            nb_sinistres_trois_ans=5,
            anciennete_permis_mois=10,
            puissance_fiscale_cv=9,
        )
    )
    assert [x.regle_id for x in r.regles] == [
        "R01_SUSPENSION",
        "R02_RESILIATIONS",
        "R03_CRM",
        "R04_SINISTRES_RESPONSABLES",
        "R05_SINISTRES_TOTAL",
        "R06_JEUNE_PERMIS_PUISSANCE",
    ]
    assert r.score == 6.0


@pytest.mark.parametrize("champ", [f.name for f in dataclasses.fields(FaitsRisque)])
def test_donnee_absente_leve_donnee_hors_bareme(champ):
    with pytest.raises(DonneeHorsBareme) as exc:
        evaluer(faits(**{champ: None}))
    assert exc.value.champ == champ


def test_motif_sans_valeur_du_dossier():
    assert (
        evaluer(faits(crm=Decimal("1.37"))).regles[0].motif
        == "Le coefficient bonus-malus dépasse 1,25."
    )
```

- [ ] **Step 3: Vérifier l'échec** — `uv run pytest fonction-calcul/tests/unit/test_bareme.py --no-cov -q` → erreurs d'import.

- [ ] **Step 4: Implémenter `evaluer`** — tous les champs vérifiés non `None` d'abord (le premier `None` dans l'ordre des champs lève `DonneeHorsBareme(champ)`), puis les six règles **dans l'ordre R01→R06**, toutes évaluées. Motifs, copie exacte :
  - `R01_SUSPENSION` : « Le relevé d'information mentionne une suspension de permis. »
  - `R02_RESILIATIONS` : « Le relevé d'information mentionne au moins deux résiliations. »
  - `R03_CRM` : « Le coefficient bonus-malus dépasse 1,25. »
  - `R04_SINISTRES_RESPONSABLES` : « Plus de deux sinistres responsables dans les 36 mois avant la date d'effet. »
  - `R05_SINISTRES_TOTAL` : « Plus de quatre sinistres dans les 36 mois avant la date d'effet. »
  - `R06_JEUNE_PERMIS_PUISSANCE` : « Permis de moins de 3 ans et véhicule de plus de 7 CV. »

- [ ] **Step 5: Vérifier le succès** — même commande → PASS.

- [ ] **Step 6: Commit** — `feat(calcul): barème déterministe bareme-2026.10-v1 (T9 #64)`.

### Task 2: Formule `calculer_prime` (domaine pur de la Function)

**Files:**
- Create: `fonction-calcul/agentinsurflow_calcul/domain/formule.py`
- Modify: `fonction-calcul/agentinsurflow_calcul/domain/models.py`
- Test: `fonction-calcul/tests/unit/test_formule.py`

**Interfaces:**
- Consumes: `DonneeHorsBareme` (tâche 1).
- Produces (`models.py`) : `FaitsPrime(formule: str | None, anciennete_permis_mois: int | None, departement: str | None, puissance_fiscale_cv: int | None, type_usage: str | None, crm: Decimal | None)`, `ResultatPrime(version_formule: str, prime_ht: Decimal, montant_taxes: Decimal, prime_ttc_annuelle: Decimal, prime_mensuelle: Decimal, coefficients: dict[str, Decimal])` (clés de `coefficients` : `prime_base`, `k_permis`, `k_zone`, `k_vehicule`, `k_usage`, `crm`, `taux_taxe`).
- Produces (`formule.py`) : `VERSION_FORMULE = "formule-2026.10-v1"`, `calculer(faits: FaitsPrime) -> ResultatPrime`.

- [ ] **Step 1: Écrire les tests qui échouent** — constructeur `faits(**s)` au défaut du seed 1 (`formule="tous_risques", anciennete_permis_mois=91, departement="75", puissance_fiscale_cv=5, type_usage="prive", crm=Decimal("0.90")`) :

```python
def test_seed_1():
    r = calculer(faits())
    assert (
        r.version_formule,
        r.prime_ht,
        r.montant_taxes,
        r.prime_ttc_annuelle,
        r.prime_mensuelle,
    ) == (
        "formule-2026.10-v1",
        Decimal("694.69"),
        Decimal("125.04"),
        Decimal("819.73"),
        Decimal("68.31"),
    )
    assert r.coefficients == {
        "prime_base": Decimal("650"),
        "k_permis": Decimal("1.00"),
        "k_zone": Decimal("1.25"),
        "k_vehicule": Decimal("1.00"),
        "k_usage": Decimal("0.95"),
        "crm": Decimal("0.90"),
        "taux_taxe": Decimal("0.18"),
    }


def test_exemple_des_sources_corrige():
    r = calculer(
        faits(
            anciennete_permis_mois=18,
            puissance_fiscale_cv=6,
            type_usage="prive_trajet",
            crm=Decimal("0.85"),
        )
    )
    assert (r.prime_ht, r.montant_taxes, r.prime_ttc_annuelle, r.prime_mensuelle) == (
        Decimal("1035.94"),
        Decimal("186.47"),
        Decimal("1222.41"),
        Decimal("101.87"),
    )


def test_taxes_plus_ht_egale_ttc(): ...  # sur une dizaine de combinaisons : prime_ht + montant_taxes == prime_ttc_annuelle


def test_demi_centime_arrondi_vers_le_haut():
    # tiers 250 × k_permis 1,00 × zone B 1,00 × 5 CV 1,00 × prive 0,95 × crm 0,51 = 121,125 → 121,13
    assert calculer(
        faits(formule="tiers", departement="69", crm=Decimal("0.51"))
    ).prime_ht == Decimal("121.13")
```
Plus des tests paramétrés : chaque `prime_base` (`tiers` 250, `tiers_etendu` 400, `tous_risques` 650) ; chaque palier `k_permis` (11→2,00 ; 12→1,50 ; 23→1,50 ; 24→1,25 ; 35→1,25 ; 36→1,00) ; `k_zone` (`75`,`92`,`93`,`94`,`13`→1,25 ; `15`,`48`,`23`→0,90 ; `69`,`2A`,`2B`,`974`,`971`→1,00) ; `k_vehicule` (4→0,90 ; 5→1,00 ; 7→1,00 ; 8→1,30 ; 10→1,30 ; 11→1,60) ; `k_usage` (`prive` 0,95, `prive_trajet` 1,00, `professionnel` 1,35) ; `DonneeHorsBareme` avec le bon `champ` pour `formule="tiers_simple"`, `type_usage="PROMENADE"`, `departement` ∈ {`"20"`, `"96"`, `"977"`, `"00"`, `""`}, et chaque champ à `None`.

- [ ] **Step 2: Vérifier l'échec** — `uv run pytest fonction-calcul/tests/unit/test_formule.py --no-cov -q` → import impossible.

- [ ] **Step 3: Implémenter `calculer`** — grilles en constantes `Decimal` (spec § 6.2) ; départements valides = `{f"{i:02d}" for i in range(1, 96) if i != 20} | {"2A", "2B"} | {str(i) for i in range(971, 977)}` ; tout `None` ou valeur hors grille → `DonneeHorsBareme(champ)`. Calcul :

```python
ht = base * k_permis * k_zone * k_vehicule * k_usage * crm
ttc = ht * (1 + TAUX_TAXE)
prime_ht, prime_ttc = _centime(ht), _centime(ttc)  # quantize(Decimal("0.01"), ROUND_HALF_UP)
montant_taxes = prime_ttc - prime_ht
prime_mensuelle = _centime(ttc / 12)
```

- [ ] **Step 4: Vérifier le succès** → PASS.

- [ ] **Step 5: Commit** — `feat(calcul): formule de prime formule-2026.10-v1 (T9 #64)`.

### Task 3: Routes HTTP de la Function, image locale et README

**Files:**
- Create: `fonction-calcul/function_app.py`, `fonction-calcul/host.json` (`{"version": "2.0"}`, préfixe de route par défaut `api`), `fonction-calcul/requirements.txt`, `fonction-calcul/Dockerfile`, `fonction-calcul/README.md`
- Modify: `docker-compose.yml` (service `calcul`), `Makefile` (cible `lint` : contrôle de `requirements.txt`)
- Test: `fonction-calcul/tests/unit/test_routes_calcul.py`, `fonction-calcul/tests/unit/test_architecture_calcul.py`

**Interfaces:**
- Consumes: `evaluer`, `calculer`, `VERSION_BAREME`, `VERSION_FORMULE`, modèles (tâches 1–2).
- Produces (contrat HTTP utilisé par la tâche 5) :
  - `POST /api/evaluer` — corps : **exactement** les 7 clés de `FaitsRisque` ; entiers JSON (pas de booléen) ou `null` ; `crm` en **chaîne** décimale ou `null`. 200 → `{"version_bareme", "classe", "decision", "score", "regles": [{"regle_id", "motif"}]}`.
  - `POST /api/calculer` — corps : exactement les 6 clés de `FaitsPrime` (chaînes pour `formule`, `departement`, `type_usage`, `crm` ; entiers pour les deux autres ; ou `null`). 200 → `{"version_formule", "prime_ht", "montant_taxes", "prime_ttc_annuelle", "prime_mensuelle", "coefficients": {…}}`, tous les montants et coefficients en chaînes (`str(Decimal)`).
  - 400 `{"code": "REQUETE_INVALIDE"}` : corps non JSON, pas un objet, clé manquante ou en trop, mauvais type, `crm` non décimal.
  - 422 `{"code": "DONNEE_HORS_BAREME", "champ": "<nom>"}`.
  - `GET /api/sante` → 200 `{"version": $APP_VERSION ou "dev", "bareme": "bareme-2026.10-v1", "formule": "formule-2026.10-v1"}`.

- [ ] **Step 1: Écrire les tests qui échouent** — appel direct des fonctions du modèle v2 :

```python
def appeler(
    nom: str, corps: object = None, methode: str = "POST", brut: bytes | None = None
) -> func.HttpResponse:
    fn = next(f for f in app.get_functions() if f.get_function_name() == nom)
    body = brut if brut is not None else (b"" if corps is None else json.dumps(corps).encode())
    return fn.get_user_function()(func.HttpRequest(methode, f"/api/{nom}", body=body))
```
Tests : `evaluer` seed 1 → 200, `decision == "ACCEPTE"`, `score == 0.0` ; `calculer` seed 1 → `prime_ttc_annuelle == "819.73"` ; `crm: null` → 422 `{"code": "DONNEE_HORS_BAREME", "champ": "crm"}` ; `type_usage: "PROMENADE"` → 422 champ `type_usage` ; paramétré 400 `REQUETE_INVALIDE` pour : `brut=b"{"`, `corps=[]`, clé `suspensions` retirée, clé `inconnu` ajoutée, `suspensions: True`, `suspensions: "1"`, `crm: 0.9` (nombre), `crm: "abc"` ; `sante` en `GET` → versions ; aucune réponse ne contient de champ autre que ceux du contrat.
`test_architecture_calcul.py` : calqué sur `serveur-mcp/tests/unit/test_architecture_mcp.py`, couche `domain` seule, `AUTORISES = sys.stdlib_module_names | {"agentinsurflow_calcul"}`.

- [ ] **Step 2: Vérifier l'échec** — `uv run pytest fonction-calcul/tests/unit --no-cov -q`.

- [ ] **Step 3: Implémenter `function_app.py`** — `app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)` (la protection est Easy Auth, spec § 3.1) ; trois `@app.route` (`evaluer` et `calculer` en `POST`, `sante` en `GET`) ; validation stricte du corps puis domaine ; `DonneeHorsBareme` → 422. **Aucun log** du corps de requête ou de réponse. Ajouter `fonction-calcul` à `pythonpath` de la racine si nécessaire pour importer `function_app`.

- [ ] **Step 4: `requirements.txt` et image** — `requirements.txt` = `uv export --package agentinsurflow-calcul --no-emit-workspace --no-dev --no-hashes` ; la cible `lint` échoue s'il n'est pas à jour (`… | diff - fonction-calcul/requirements.txt`). `Dockerfile` : `FROM mcr.microsoft.com/azure-functions/python:4-python3.12`, `AzureWebJobsScriptRoot=/home/site/wwwroot`, `pip install -r requirements.txt`, copie de `function_app.py`, `host.json`, `agentinsurflow_calcul/`. Service compose `calcul` : `build: { context: ., dockerfile: fonction-calcul/Dockerfile }`, `APP_VERSION: dev`, **aucun port publié**.

- [ ] **Step 5: Vérifier** — tests verts ; `docker compose build calcul && docker compose up -d calcul` puis `docker compose exec serveur-mcp python -c "import httpx; print(httpx.get('http://calcul:80/api/sante').json())"` → les deux versions.

- [ ] **Step 6: README** (`fonction-calcul/README.md`) : barème (tableau R01–R06), formule et grilles, **taux de taxe de 18 % fictif**, date de référence, erreurs 400/422, versionnement (un changement = nouvelle version + commit + redéploiement), exécution locale.

- [ ] **Step 7: Commit** — `feat(calcul): routes evaluer, calculer et sante de la Function (T9 #64)`.

### Task 4: Vue minimisée et `VueContrat` étendues (underwriting-admin)

**Files:**
- Modify: `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Infrastructure/Dossiers/VueMinimisee.cs` (nouvelle constante `CreerCalcul` ; **ne pas modifier** `Creer`, utilisée par la migration `VueEtDroits`), `…/Dossiers/Entites.cs` (`LigneVue`), `…/Dossiers/DepotDossiersEf.cs` (`Vers`), `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Domain/VueContrat.cs`
- Create: migration `…/Dossiers/Migrations/<horodatage>_VueCalcul.cs` (+ `.Designer.cs`, snapshot mis à jour) par `dotnet ef migrations add VueCalcul`
- Test: `underwriting-admin/tests/AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests/DossiersPostgresTests.cs`, `underwriting-admin/tests/AgentInsurFlow.UnderwritingAdmin.Api.Tests/ContratsTests.cs`, tests qui construisent un `VueContrat` (Application, Domain)

**Interfaces:**
- Produces : `VueContrat` gagne, **à la fin** : `DateOnly DateEffet, int? AnciennetePermisMois, int? PuissanceFiscaleCv, string? TypeUsage, int NbSinistresTroisAns, int NbSinistresResponsablesTroisAns` → JSON `date_effet` (`"2026-01-01"`), `anciennete_permis_mois`, `puissance_fiscale_cv`, `type_usage`, `nb_sinistres_trois_ans`, `nb_sinistres_responsables_trois_ans`. Champs existants et leurs noms JSON inchangés (rag les lit).

- [ ] **Step 1: Écrire les tests qui échouent**
  - `Vue_n_expose_aucune_donnee_personnelle` : liste attendue des colonnes = l'actuelle + `anciennete_permis_mois`, `date_effet`, `nb_sinistres_responsables_trois_ans`, `nb_sinistres_trois_ans`, `puissance_fiscale_cv`, `type_usage`.
  - Nouveau `Vue_calcule_les_faits_du_calcul_a_la_date_d_effet` (seeds) : `AIF-2026-000001` → `anciennete_permis_mois = 91`, `puissance_fiscale_cv = 5`, `type_usage = "prive"`, `nb_sinistres_trois_ans = 0` ; `AIF-2026-000004` → `anciennete_permis_mois = 70`, `nb_sinistres_trois_ans = 2`, `nb_sinistres_responsables_trois_ans = 2`.
  - Nouveau `Vue_sans_vehicule_rend_puissance_et_usage_nuls` : contrat inséré sans véhicule (compte migrateur, transaction annulée) → `puissance_fiscale_cv` et `type_usage` `NULL`.
  - Nouveau `Vue_ne_compte_pas_un_sinistre_hors_des_trois_ans` : sinistre daté de `date_effet − 37 mois` et un à `date_effet` même → aucun des deux compté ; un à taux 0 compté dans le total seulement.
  - `ContratsTests` : la réponse de `GET /api/contrats/AIF-2026-000001` contient les six clés JSON ci-dessus.

- [ ] **Step 2: Vérifier l'échec** — `PATH="$HOME/.dotnet:$PATH" dotnet test underwriting-admin` → échecs sur les colonnes.

- [ ] **Step 3: Implémenter** — `CreerCalcul` = `CREATE OR REPLACE VIEW vue_contrat_minimisee AS` avec les colonnes actuelles **identiques et dans le même ordre**, puis à la fin :

```sql
c.date_effet,
(date_part('year', age(c.date_effet, s.permis_date_obtention)) * 12
 + date_part('month', age(c.date_effet, s.permis_date_obtention)))::int AS anciennete_permis_mois,
v.puissance_fiscale_cv,
v.type_usage,
(SELECT count(*) FROM sinistre si WHERE si.releve_information_id = r.id
   AND si.date_sinistre >= c.date_effet - interval '36 months' AND si.date_sinistre < c.date_effet)::int AS nb_sinistres_trois_ans,
(SELECT count(*) FROM sinistre si WHERE si.releve_information_id = r.id
   AND si.date_sinistre >= c.date_effet - interval '36 months' AND si.date_sinistre < c.date_effet
   AND si.taux_responsabilite > 0)::int AS nb_sinistres_responsables_trois_ans
-- … FROM inchangé, plus :
LEFT JOIN LATERAL (SELECT puissance_fiscale_cv, type_usage FROM vehicule
                   WHERE contrat_id = c.id ORDER BY puissance_fiscale_cv DESC LIMIT 1) v ON true
```
Migration `VueCalcul` : `Up` = `Sql(VueMinimisee.CreerCalcul)` puis `Sql(VueMinimisee.Droits)` ; `Down` = `Sql(VueMinimisee.Supprimer)`, `Sql(VueMinimisee.Creer)`, `Sql(VueMinimisee.Droits)` (`CREATE OR REPLACE` ne retire pas de colonne). `LigneVue`, `Vers` et `VueContrat` suivent.

- [ ] **Step 4: Vérifier** — `dotnet test underwriting-admin` → PASS ; `uv run pytest rag/tests --no-cov -q` → rag inchangé et vert.

- [ ] **Step 5: Commit** — `feat(underwriting-admin): vue minimisée étendue aux faits du calcul (T9 #64)`.

### Task 5: Outils MCP `evaluer_risque` et `calculer_prime`

**Files:**
- Modify: `serveur-mcp/agentinsurflow_mcp/domain/models.py`, `domain/ports.py`, `application/outils.py`, `api/serveur.py`, `api/app.py`, `serveur-mcp/tests/fakes_mcp.py`, les 4 appels `ServeurMcp(` des tests, `docker-compose.yml` (service `serveur-mcp` : `CALCUL_URL: http://calcul:80`), `.env.example` (`CALCUL_URL=`, `CALCUL_AUDIENCE=`)
- Create: `serveur-mcp/agentinsurflow_mcp/domain/faits.py`, `serveur-mcp/agentinsurflow_mcp/infrastructure/fonction_calcul/__init__.py`, `…/fonction_calcul/client.py`
- Test: `serveur-mcp/tests/unit/test_outils_calcul.py`, `serveur-mcp/tests/unit/test_client_calcul.py`, `serveur-mcp/tests/integration/test_outils_calcul.py`

**Interfaces:**
- Consumes: contrat HTTP de la tâche 3 ; clés JSON de `VueContrat` de la tâche 4.
- Produces :
  - `models.py` : `CALCUL_INDISPONIBLE = "CALCUL_INDISPONIBLE"`, `DONNEE_HORS_BAREME = "DONNEE_HORS_BAREME"`.
  - `ports.py` : `class CalculateurPort(Protocol)` avec `async def evaluer(self, faits: dict[str, Any]) -> dict[str, Any]` et `async def calculer(self, faits: dict[str, Any]) -> dict[str, Any]`.
  - `faits.py` : `faits_risque(contrat: dict[str, Any]) -> dict[str, Any]` et `faits_prime(contrat: dict[str, Any]) -> dict[str, Any]` — reprennent les clés du contrat HTTP de la tâche 3 depuis la vue (`crm` ← `crm_bonus_malus`, `formule`, `departement` tels quels) ; une clé absente de la vue ou `None` → `None` ; `crm` converti par `str(valeur)`.
  - `outils.py` : `async def evaluer_risque(appelant, jetons, dossiers, calculateur, numero_contrat) -> dict[str, Any]` et `async def calculer_prime(...)` (même signature) : OBO `underwriting` → `lire_contrat` → `faits_*` → `calculateur.*` ; renvoient le résultat de la Function tel quel.
  - `client.py` : `ConfigCalcul(BaseSettings)` (`calcul_url: str = "http://localhost:7071"`, `calcul_audience: str | None`, `azure_tenant_id: str | None`, `mcp_api_client_id: str | None`, `azure_uami_client_id: str | None`) et `class ClientCalcul(http: httpx.AsyncClient, cfg: ConfigCalcul)` qui implémente le port.
  - `ServeurMcp(jetons, corpus, dossiers, calculateur, nom="agentinsurflow-mcp")`.

- [ ] **Step 1: Écrire les tests unitaires qui échouent**
  - `test_outils_calcul.py` (fakes : `FauxDossiers(vue=...)` renvoie la vue fournie ; nouveau `FauxCalculateur(erreur=None)` qui enregistre `appels: list[tuple[str, dict]]`) :
    - `faits_risque(VUE_SEED_1) == {"suspensions": 0, "resiliations": 0, "crm": "0.9", "nb_sinistres_responsables_trois_ans": 0, "nb_sinistres_trois_ans": 0, "anciennete_permis_mois": 91, "puissance_fiscale_cv": 5}` ;
    - `faits_prime(VUE_SEED_1) == {"formule": "tous_risques", "anciennete_permis_mois": 91, "departement": "75", "puissance_fiscale_cv": 5, "type_usage": "prive", "crm": "0.9"}` ;
    - vue sans `puissance_fiscale_cv` ni `type_usage` (ou à `None`) → ces faits valent `None` (la Function rendra 422) ;
    - `evaluer_risque` : `jetons.demandes == [("jeton-entrant", "underwriting")]`, `calculateur.appels == [("evaluer", faits_risque(VUE_SEED_1))]` ; `calculer_prime` : idem avec `"calculer"` ;
    - `CONTRAT_INTROUVABLE` de `lire_contrat` → propagé, `calculateur.appels == []`.
  - `test_client_calcul.py` (`httpx.MockTransport`, même style que `test_client_gateway.py`) :
    - 200 → le JSON ; requête `POST {calcul_url}/api/evaluer` (ou `/api/calculer`) avec le corps des faits ;
    - 422 `{"code": "DONNEE_HORS_BAREME", "champ": "type_usage"}` → `ErreurOutil(DONNEE_HORS_BAREME)` dont le message nomme `type_usage` ;
    - 400, 401, 500, `httpx.ConnectError`, `httpx.ReadTimeout` → `ErreurOutil(CALCUL_INDISPONIBLE)` ;
    - sans `calcul_audience` : aucun en-tête `Authorization` ; avec `calcul_audience` et un fournisseur de jeton simulé : `Authorization: Bearer <jeton>` ;
    - le délai du client vaut 10 s ;
    - span `calcul.appeler` : attributs `calcul.route`, `http.status_code`, `resultat.code`, et `bareme.version` / `formule.version` sur succès ; **aucun** attribut ne contient une valeur des faits ni du résultat (vérifier `"0.9"`, `"819.73"`, `"ACCEPTE"` absents).

- [ ] **Step 2: Écrire les tests d'intégration qui échouent** — `test_outils_calcul.py`, même harnais que `test_outils_lecture.py` (`session_mcp`, `creer(AZP_…)`) :
  - orchestrateur → `evaluer_risque` : `isError is False`, `structuredContent` = réponse du `FauxCalculateur` ;
  - actuaire → `calculer_prime` : idem ;
  - orchestrateur → `calculer_prime`, actuaire → `evaluer_risque`, rédacteur → l'un et l'autre : `(True, {"code": "UNAUTHORIZED_TOOL"})`, `FauxCalculateur.appels == []` ;
  - `list_tools` pour l'actuaire → `["calculer_prime"]` ;
  - paramétré `DONNEE_HORS_BAREME`, `CALCUL_INDISPONIBLE`, `CONTRAT_INTROUVABLE` → `(True, {"code": code})` ;
  - les docstrings citent `DONNEE_HORS_BAREME` et `CALCUL_INDISPONIBLE`.

- [ ] **Step 3: Vérifier l'échec** — `uv run pytest serveur-mcp/tests --no-cov -q`.

- [ ] **Step 4: Implémenter** — modèles, port, `faits.py`, cas d'usage ; deux `@self.tool()` dans `ServeurMcp`, docstrings (copie) :
  - `evaluer_risque(numero_contrat: str)` : « Évalue le risque d'un contrat avec le barème déterministe versionné : classe, décision proposée (ACCEPTE ou REFUSE), score (nombre de règles déclenchées) et règles déclenchées avec leur motif. Ne décide rien : la décision reste soumise au gestionnaire. Erreur CONTRAT_INTROUVABLE si le numéro est inconnu, DONNEE_HORS_BAREME si une donnée du contrat manque ou sort du barème (revue humaine), CALCUL_INDISPONIBLE si le calcul ne répond pas. »
  - `calculer_prime(numero_contrat: str)` : « Calcule la prime annuelle et mensuelle d'un contrat avec la formule versionnée, et le détail des coefficients. Montants en euros, en texte décimal. Erreur CONTRAT_INTROUVABLE si le numéro est inconnu, DONNEE_HORS_BAREME si une donnée du contrat manque ou sort de la formule (revue humaine), CALCUL_INDISPONIBLE si le calcul ne répond pas. »
  
  `ClientCalcul` : `httpx` avec `timeout=10.0` ; jeton = `None` sans `calcul_audience`, sinon `ClientAssertionCredential(azure_tenant_id, mcp_api_client_id, func=<jeton de ManagedIdentityCredential(client_id=azure_uami_client_id) pour PORTEE_FEDERATION>)` (même assertion que `infrastructure/entra/obo.py`) puis `get_token(f"{calcul_audience}/.default")`, hors boucle par `run_in_threadpool`, credential créé une fois ; `AzureError` ou configuration incomplète → `CALCUL_INDISPONIBLE`. Un 400 est journalisé en erreur (`"requête de calcul invalide"`, sans corps). `traceparent` injecté comme dans `ClientGateway`. Câblage dans `_serveur_reel()` (`api/app.py`).

- [ ] **Step 5: Vérifier** — `uv run pytest serveur-mcp/tests --no-cov -q` → PASS ; `make lint` ; parcours local : `make up`, puis un appel `evaluer_risque` sur `AIF-2026-000001` avec un jeton d'orchestrateur (même procédure que le parcours de la PR #66) → `ACCEPTE`, score 0.

- [ ] **Step 6: Commit** — `feat(mcp): outils evaluer_risque et calculer_prime via la Function de calcul (T9 #64)`.

### Task 6: Infra, déploiement et documentation

**Files:**
- Create: `infra/calcul.sh`
- Modify: `Makefile` (cible `calcul`), `.github/workflows/deploy.yml`, `infra/containerapp.yaml` (env `CALCUL_URL`, `CALCUL_AUDIENCE` du conteneur `serveur-mcp`), `.env.example` (`CALCUL_APP_STAGING=`, `CALCUL_APP_PRODUCTION=`, `CALCUL_STORAGE=`), `docs/superpowers/specs/2026-10-21-serveur-mcp-design.md`, `serveur-mcp/README.md`

**Interfaces:**
- Consumes: routes de la tâche 3 ; variables `CALCUL_URL`, `CALCUL_AUDIENCE` de la tâche 5.
- Produces : variables d'environnement GitHub, par environnement (`staging`, `production`) : `CALCUL_APP_NAME`, `CALCUL_URL`, `CALCUL_AUDIENCE`.

- [ ] **Step 1: `infra/calcul.sh`** (style de `infra/bootstrap.sh` : `set -euo pipefail`, variables vérifiées, idempotent, `existe()`) :
  1. compte de stockage `CALCUL_STORAGE` ; Function Apps `CALCUL_APP_STAGING` et `CALCUL_APP_PRODUCTION` en **Flex Consumption** (`az functionapp create --flexconsumption-location "$AZURE_LOCATION" --runtime python --runtime-version 3.12 …`) ;
  2. inscription Entra `agentinsurflow-calcul`, `identifierUris = ["api://<appId>"]` (comme `inscrire()` d'`infra/entra.sh`) ;
  3. Easy Auth (`az rest --method put …/config/authsettingsV2`) : fournisseur Entra, `allowedAudiences = ["api://<appId calcul>"]`, `defaultAuthorizationPolicy.allowedApplications = [MCP_API_CLIENT_ID]`, `unauthenticatedClientAction = Return401`, `globalValidation.excludedPaths = ["/api/sante"]` ;
  4. affiche les valeurs à poser en variables GitHub. **Lancé à la main par Acerola** (`make calcul`), jamais par un agent.
  
  Vérification : `bash -n infra/calcul.sh` et `shellcheck infra/calcul.sh` propres.

- [ ] **Step 2: `deploy.yml`** — dans le job `deploy`, **avant** « Déployer (modèle infra/containerapp.yaml…) » :
  - `actions/checkout@v4` avec `ref: ${{ steps.image.outputs.tag }}`, `path: calcul-src` (un rollback redéploie le code de la Function du même commit que les images) ;
  - « Déployer la Function de calcul » : zip de `function_app.py`, `host.json`, `requirements.txt`, `agentinsurflow_calcul/` ; `az functionapp config appsettings set … APP_VERSION=<tag>` ; `az functionapp deployment source config-zip -g "$RG" -n "$CALCUL_APP_NAME" --src calcul.zip --build-remote true` ;
  - « Fumée de la Function » (bloquante) : boucle sur `GET $CALCUL_URL/api/sante` jusqu'à `version == tag` (30 × 5 s) ; puis `POST $CALCUL_URL/api/evaluer` sans jeton → `401`.
  - Étape « Déployer » : `CALCUL_URL` et `CALCUL_AUDIENCE` passés à la substitution de `infra/containerapp.yaml`.
  
  Vérification : `actionlint .github/workflows/deploy.yml` (s'il est installé) sinon relecture ; aucune valeur en dur.

- [ ] **Step 3: Documentation** — spec MCP : § 2 (anti-objectif : « hors export OTLP **et appel de la Function de calcul** »), § 4 (flèche MCP → Function dans le schéma), § 5.1 (cibles des deux outils), § 5.3 remplacé par un renvoi à la spec du calcul, § 6 (codes `CALCUL_INDISPONIBLE`, `DONNEE_HORS_BAREME`) ; `serveur-mcp/README.md` : les deux outils et `CALCUL_URL` / `CALCUL_AUDIENCE`. Hors dépôt, à faire par Acerola : exception à D22 dans `brief1/journal-decisions.md`.

- [ ] **Step 4: Vérifier** — `make lint && make test && make test-integration` → verts, couverture ≥ 80 %.

- [ ] **Step 5: Commit** — `feat(infra): Function de calcul en Flex Consumption, Easy Auth et déploiement (T9 #64)` ; push de `feat/RiskPrime` ; PR en brouillon vers `feat/mcp`.
