# Barème citable (#99) et jeu agrégé unique (#52) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Générer les procédures internes depuis une table déclarative du barème (via un instantané versionné), puis fusionner Légifrance + barème + documents rédigés en un seul jeu agrégé qui alimente l'ingestion jusqu'en production.

**Architecture:** `fonction-calcul` expose `REGLES` (table) et écrit `data/raw/bareme-2026.10-v1.json`. Le paquet `rag` lit **ce fichier** (jamais le code de `fonction-calcul`), génère les 6 procédures fusionnées (fonction pure de `domain/`), agrège les trois sources dans `data/aggregated/corpus-<date Légifrance>.json` (CLI `cli/agreger.py`), et `cli/ingest.py --jeu` l'envoie collection par collection.

**Tech Stack:** Python 3 (stdlib seulement pour le nouveau code), pytest, uv workspace, Makefile, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-29-bareme-agregation-design.md`

## Global Constraints

- `VERSION_BAREME = "bareme-2026.10-v1"` inchangée ; motifs des 6 règles inchangés au caractère près ; résultats d'`evaluer()` identiques (tests `fonction-calcul/tests/unit/test_bareme.py` verts **sans modification**).
- `rag` n'importe jamais `agentinsurflow_calcul` : le lien est `data/raw/bareme-*.json`.
- Aucune nouvelle dépendance. `domain/` des deux paquets : bibliothèque standard seulement (tests d'architecture existants).
- Déterminisme : aucune date du jour dans un fichier généré ; régénérer = mêmes octets. JSON écrit avec `json.dumps(..., ensure_ascii=False, indent=1)` et écriture atomique (`.tmp` + `os.replace`), comme `sauvegarder_instantane`.
- sha256 = `sha_articles` de `rag/agentinsurflow_rag/cli/ingest.py` (JSON canonique : `sort_keys=True, ensure_ascii=False, separators=(",", ":")`). Côté `fonction-calcul`, même calcul réécrit (pas d'import croisé).
- `doc_id` des procédures inchangé (`PI-<regle_id>`) ; `version` devient `PI-<regle_id>-bareme-2026.10-v1` ; `article` = `PI-` + `regle_id` avec `_`→`-` ; `date_debut` = `DATE_BAREME = "2026-10-26"`.
- Les articles abrogés restent dans le jeu ; seules les entrées corrompues sont écartées, avec leur raison.
- Conventions du dépôt : code, messages et docs en français ; commits `feat:`/`docs:`/`test:` + ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Écart assumé avec la conception (choix du rédacteur n° 3)** : on **ne réordonne pas** `nettoyer()`. L'agrégation l'appelle sur `{**brut, "etat": "VIGUEUR"}` : tous les contrôles (partiel, vide, trop court, date) et la normalisation s'appliquent, puis l'état d'origine est rétabli. Le code serveur ne change pas. **Format** : un seul fichier JSON `{manifeste, entrees}` (même forme que les instantanés, sha vérifié à la lecture) au lieu de `.jsonl` + manifeste séparé.

## Review Focus

1. Un fichier rédigé dont le `regle_id` n'existe pas au barème (ou une règle sans fichier rédigé) → erreur qui nomme le `regle_id`, jamais un jeu partiel. *(Task 3)*
2. Un abrogé dont la date est malformée → écarté `date_invalide` (il ne doit pas passer grâce à l'exception « abrogé »). *(Task 4)*
3. Un jeu agrégé modifié à la main après génération → `make ingest JEU=…` refuse (sha ≠ manifeste), code 1. *(Task 5)*
4. `--jeu` combiné à `--instantane` ou `--source` → message clair, code 1 (pas d'envoi ambigu). *(Task 5)*
5. Barème modifié sans régénérer l'instantané (ou instantané sans régénérer le jeu) → test rouge en CI et étape `deploy.yml` en échec. *(Tasks 2, 4, 6)*

---

### Task 1: Table déclarative `REGLES` dans le barème

**Files:**
- Modify: `fonction-calcul/agentinsurflow_calcul/domain/bareme.py`
- Test: `fonction-calcul/tests/unit/test_bareme.py` (ajouts seulement)

**Interfaces:**
- Produces (dans `bareme.py`) :
  - `Operateur = Literal[">=", ">", "<"]`
  - `@dataclass(frozen=True) class Condition: champ: str; operateur: Operateur; seuil: Decimal`
  - `@dataclass(frozen=True) class Regle: regle_id: str; libelle: str; conditions: tuple[Condition, ...]; motif: str; effet: Literal["REFUSE"]`
  - `REGLES: tuple[Regle, ...]` (ordre R01→R06), `DATE_BAREME = "2026-10-26"`, `VERSION_BAREME` inchangée
  - `evaluer(faits)` : même signature, s'appuie sur `REGLES` (une règle est déclenchée si **toutes** ses conditions sont vraies ; opérateurs via le module `operator`). Les contrôles `DonneeHorsBareme` et `verifier_crm` restent en tête, inchangés ; la valeur comparée pour `crm` est celle renvoyée par `verifier_crm`.

Valeurs (libellés = titres actuels des procédures) :

| regle_id | libelle | conditions |
|---|---|---|
| R01_SUSPENSION | Suspension de permis | suspensions >= 1 |
| R02_RESILIATIONS | Résiliations antérieures | resiliations >= 2 |
| R03_CRM | Coefficient bonus-malus élevé | crm > 1.25 |
| R04_SINISTRES_RESPONSABLES | Sinistres responsables répétés | nb_sinistres_responsables_trois_ans > 2 |
| R05_SINISTRES_TOTAL | Fréquence de sinistres élevée | nb_sinistres_trois_ans > 4 |
| R06_JEUNE_PERMIS_PUISSANCE | Jeune permis et véhicule puissant | anciennete_permis_mois < 36 **et** puissance_fiscale_cv > 7 |

- [ ] **Step 1: Write the failing tests**

```python
from agentinsurflow_calcul.domain.bareme import REGLES, Condition
# FaitsRisque, evaluer et faits() sont déjà importés / définis en tête de test_bareme.py


def test_table_regles_ordre_et_seuils():
    assert [r.regle_id for r in REGLES] == [
        "R01_SUSPENSION",
        "R02_RESILIATIONS",
        "R03_CRM",
        "R04_SINISTRES_RESPONSABLES",
        "R05_SINISTRES_TOTAL",
        "R06_JEUNE_PERMIS_PUISSANCE",
    ]
    assert REGLES[2].conditions == (Condition("crm", ">", Decimal("1.25")),)
    assert REGLES[5].conditions == (
        Condition("anciennete_permis_mois", "<", Decimal(36)),
        Condition("puissance_fiscale_cv", ">", Decimal(7)),
    )
    assert {r.effet for r in REGLES} == {"REFUSE"}


def test_chaque_champ_de_condition_existe_dans_les_faits():
    champs = {f.name for f in dataclasses.fields(FaitsRisque)}
    assert {c.champ for r in REGLES for c in r.conditions} <= champs


def test_motif_rendu_est_celui_de_la_table():
    r = evaluer(faits(suspensions=1))
    assert (
        r.regles[0].motif
        == REGLES[0].motif
        == "Le relevé d'information mentionne une suspension de permis."
    )
```

- [ ] **Step 2: Run** `uv run pytest fonction-calcul/tests/unit/test_bareme.py --no-cov -q` → FAIL (`ImportError: REGLES`).
- [ ] **Step 3: Implement** la table et la réécriture d'`evaluer()` (motifs recopiés à l'identique du code actuel).
- [ ] **Step 4: Run** `uv run pytest fonction-calcul/tests/unit --no-cov -q` → tous verts, y compris les tests d'avant **non modifiés** ; puis `make lint` → OK (mypy inclus).
- [ ] **Step 5: Commit** `feat(calcul): barème en table déclarative REGLES (#99)`

---

### Task 2: Instantané versionné du barème

**Files:**
- Create: `fonction-calcul/agentinsurflow_calcul/instantane.py` (hors `domain/` : il écrit un fichier)
- Create: `fonction-calcul/tests/unit/test_instantane_bareme.py`
- Create (généré, versionné): `data/raw/bareme-2026.10-v1.json`
- Modify: `Makefile` (cible `bareme`, ajoutée à `.PHONY`)

**Interfaces:**
- Consumes: `REGLES`, `VERSION_BAREME`, `DATE_BAREME` (Task 1).
- Produces:
  - `serialiser() -> dict[str, Any]` → `{"manifeste": {"version_bareme", "date_debut", "regles": 6, "sha256"}, "regles": [{"regle_id", "libelle", "conditions": [{"champ", "operateur", "seuil"}], "motif", "effet"}]}` ; `seuil` en **texte** (`str(Decimal)`, ex. `"1.25"`, `"36"`) ; `sha256` = JSON canonique de la liste `regles`.
  - `ecrire(dossier: Path) -> Path` → `dossier / f"{VERSION_BAREME}.json"`, écriture atomique.
  - `main(argv) -> int`, option `--dossier` (défaut `data/raw`), imprime `✔ <chemin> (6 règles)`.
  - Makefile : `bareme: ## instantané du barème → data/raw/bareme-<version>.json` → `PYTHONPATH=fonction-calcul uv run python -m agentinsurflow_calcul.instantane`.
  - **Format du fichier lu par `rag` (Tasks 3, 4)** : celui de `serialiser()`.

- [ ] **Step 1: Write the failing tests**

```python
RACINE = Path(__file__).resolve().parents[3]
VERSIONNE = RACINE / "data/raw" / f"{VERSION_BAREME}.json"


def test_instantane_versionne_existe_pour_la_version_du_code():
    assert VERSIONNE.exists(), "lancer « make bareme » et versionner le fichier"


def test_regenere_identique_au_versionne(tmp_path):
    assert ecrire(tmp_path).read_bytes() == VERSIONNE.read_bytes()


def test_manifeste_et_seuils_en_texte():
    contenu = serialiser()
    assert contenu["manifeste"]["regles"] == 6
    assert contenu["manifeste"]["date_debut"] == "2026-10-26"
    assert contenu["regles"][2]["conditions"] == [
        {"champ": "crm", "operateur": ">", "seuil": "1.25"}
    ]
```

- [ ] **Step 2: Run** `uv run pytest fonction-calcul/tests/unit/test_instantane_bareme.py --no-cov -q` → FAIL (module absent).
- [ ] **Step 3: Implement** `instantane.py` et la cible Makefile.
- [ ] **Step 4: Run** `make bareme` → `✔ data/raw/bareme-2026.10-v1.json (6 règles)` ; relancer : `git status --porcelain data/raw` ne change plus ; puis les tests → PASS. Vérifier que le test casse si on change temporairement un motif dans `REGLES` (puis annuler).
- [ ] **Step 5: Commit** `feat(calcul): instantané versionné du barème data/raw/bareme-2026.10-v1.json (#99)` (inclure le fichier JSON).

---

### Task 3: Procédures fusionnées (génération) et fichiers rédigés réduits

**Files:**
- Create: `rag/agentinsurflow_rag/domain/procedures.py` (pur, stdlib)
- Modify: `rag/agentinsurflow_rag/cli/ingest.py` (extraire de `lire_markdown` un helper `lire_en_tete(fichier: Path) -> tuple[dict[str, str], str]` qui rend en-tête et corps ; `lire_markdown` l'utilise, comportement inchangé)
- Modify: les 6 `rag/corpus/procedures_internes/R0x_*.md`
- Test: `rag/tests/unit/test_procedures.py`

**Interfaces:**
- Produces (`domain/procedures.py`) :
  - `class ErreurProcedures(ValueError)`
  - `condition_lisible(conditions: Sequence[Mapping[str, str]]) -> str` : `>=`→« au moins », `>`→« plus de », `<`→« moins de » ; seuil décimal avec virgule (`"1.25"`→`1,25`) ; plusieurs conditions jointes par « et » ; forme `` `champ` plus de 1,25 ``.
  - `generer(bareme: Mapping[str, Any], rediges: Mapping[str, str], url_depot: str) -> list[dict[str, Any]]` : une entrée par règle, dans l'ordre du barème, champs `doc_id`, `version`, `article`, `date_debut`, `etat="VIGUEUR"`, `regle_id`, `texte_html`, `url_source=f"{url_depot}/procedures_internes/{regle_id}.md"`. Lève `ErreurProcedures` nommant le `regle_id` si : règle sans rédigé, rédigé sans règle, marqueur `{…}` restant après remplacement de `{version_bareme}`.
  - `texte_html` (exact) :

```
# Procédure interne {regle_id} — {libelle}

Document fictif rédigé pour le projet AgentInsurFlow.

## Règle
Condition : {condition_lisible}.
Motif retenu par le barème : « {motif} »
Effet : {effet} (barème {version_bareme}).

{corps rédigé, {version_bareme} remplacé}
```

- Fichiers rédigés (nouveau format) : en-tête `---\nregle_id: R0x_…\n---`, puis le texte actuel **à partir de** `## Pièces à vérifier` (titre, mention « Document fictif » et section `## Règle` supprimés : ils sont générés) ; dans `## Décision`, `(barème bareme-2026.10-v1)` → `(barème {version_bareme})`. Le reste du texte, mot pour mot.

- [ ] **Step 1: Write the failing tests**

```python
BAREME = {
    "manifeste": {"version_bareme": "bareme-test", "date_debut": "2026-10-26"},
    "regles": [
        {
            "regle_id": "R03_CRM",
            "libelle": "CRM élevé",
            "motif": "Le CRM dépasse 1,25.",
            "effet": "REFUSE",
            "conditions": [{"champ": "crm", "operateur": ">", "seuil": "1.25"}],
        }
    ],
}


def test_generer_champs_et_texte():
    [doc] = generer(BAREME, {"R03_CRM": "## Décision\nBarème {version_bareme}."}, "https://x")
    assert (doc["doc_id"], doc["version"], doc["article"], doc["date_debut"], doc["regle_id"]) == (
        "PI-R03_CRM",
        "PI-R03_CRM-bareme-test",
        "PI-R03-CRM",
        "2026-10-26",
        "R03_CRM",
    )
    assert "Condition : `crm` plus de 1,25." in doc["texte_html"]
    assert "Motif retenu par le barème : « Le CRM dépasse 1,25. »" in doc["texte_html"]
    assert doc["texte_html"].endswith("## Décision\nBarème bareme-test.")


def test_condition_composee():
    assert (
        condition_lisible(
            [
                {"champ": "a", "operateur": "<", "seuil": "36"},
                {"champ": "b", "operateur": ">", "seuil": "7"},
            ]
        )
        == "`a` moins de 36 et `b` plus de 7"
    )


@pytest.mark.parametrize("rediges", [{}, {"R03_CRM": "x", "R99_X": "y"}, {"R03_CRM": "{inconnu}"}])
def test_incoherence_leve_une_erreur_qui_nomme_la_regle(rediges):
    with pytest.raises(ErreurProcedures, match="R03_CRM|R99_X"):
        generer(BAREME, rediges, "https://x")


def test_corpus_reel_un_document_par_regle_id():
    # data/raw/bareme-*.json (dernier) + rag/corpus/procedures_internes via lire_en_tete
    docs = generer(bareme_reel, rediges_reels, URL_DEPOT)
    assert [d["regle_id"] for d in docs] == [r["regle_id"] for r in bareme_reel["regles"]]
    assert len({d["doc_id"] for d in docs}) == 6
    assert all("{" not in d["texte_html"] for d in docs)
```

- [ ] **Step 2: Run** `uv run pytest rag/tests/unit/test_procedures.py --no-cov -q` → FAIL (module absent).
- [ ] **Step 3: Implement** `domain/procedures.py`, le helper `lire_en_tete`, et réécrire les 6 fichiers rédigés.
- [ ] **Step 4: Run** `uv run pytest rag/tests --no-cov -q -m "not lent"` → verts (dont `test_architecture.py` et les tests `lire_markdown` existants). Relire un document généré (R06) en entier : le texte métier d'origine est intact.
- [ ] **Step 5: Commit** `feat(rag): procédures internes générées depuis l'instantané du barème (#99)`

---

### Task 4: Script d'agrégation et jeu unique versionné

**Files:**
- Create: `rag/agentinsurflow_rag/cli/agreger.py`
- Create (généré, versionné): `data/aggregated/corpus-2026-10-27.json`
- Modify: `Makefile` (cible `agreger`, `.PHONY`)
- Test: `rag/tests/unit/test_agreger.py`

**Interfaces:**
- Consumes: `lire_instantane`, `lire_markdown`, `lire_en_tete`, `sha_articles`, `URL_DEPOT`, `ErreurEnvoi` (`cli/ingest.py`) ; `nettoyer` (`domain/corpus.py`) ; `generer`, `ErreurProcedures` (Task 3).
- Produces:
  - `normaliser(brut: Mapping[str, Any]) -> dict[str, Any] | str` : `str` = raison d'écart. `etat` vide → `"partiel:etat"` ; sinon `nettoyer({**brut, "etat": "VIGUEUR"})` ; `Rejet` → sa raison ; `ArticlePropre` → entrée `{doc_id, version, article (normalisé), date_debut (ISO ou None), etat (d'origine, `strip().upper()`), texte_html (d'origine), url_source, regle_id, collection, source}`.
  - `agreger(legifrance: Path, bareme: Path, notices: Path, procedures: Path) -> dict[str, Any]` → `{"manifeste": {...}, "entrees": [...]}` ; ordre : Légifrance, notices, procédures ; `doc_id` en double → `ErreurEnvoi` qui le nomme.
  - Manifeste : `date` (= date du manifeste Légifrance), `entrees`, `par_collection`, `par_source` (`legifrance`, `redige`, `bareme`), `sources` (`{"legifrance": sha, "bareme": sha}` des instantanés lus), `ecarts` (`[{"doc_id", "source", "raison"}]`), `sha256` (= `sha_articles(entrees)`).
  - `ecrire_jeu(jeu, dossier: Path) -> Path` → `dossier / f"corpus-{date}.json"`, atomique.
  - `main(argv) -> int` : `--legifrance` / `--bareme` (défaut : dernier `data/raw/code-assurances-*.json` / `data/raw/bareme-*.json` par tri), `--notices rag/corpus/notices_produits`, `--procedures rag/corpus/procedures_internes`, `--dossier data/aggregated` ; `✔ <chemin> (N entrées, K écarts)` ; code 1 sur `ErreurEnvoi`, `ErreurProcedures`, `OSError`, `KeyError`, `ValueError`.
  - Makefile : `agreger: ## Légifrance + barème + documents rédigés → data/aggregated/corpus-<date>.json` → `uv run python -m agentinsurflow_rag.cli.agreger`.

- [ ] **Step 1: Write the failing tests**

```python
def test_abroge_conserve_etat_d_origine():
    assert normaliser(brut(etat=" abroge "))["etat"] == "ABROGE"


def test_abroge_a_date_malformee_ecarte():
    assert normaliser(brut(etat="ABROGE", date_debut="31/12/2003")) == "date_invalide"


@pytest.mark.parametrize(
    "champ,raison", [("texte_html", "partiel:texte_html"), ("etat", "partiel:etat")]
)
def test_partiel_ecarte(champ, raison):
    assert normaliser(brut(**{champ: ""})) == raison


def test_formats_homogeneises():
    e = normaliser(brut(article=" l 211-1 ", date_debut="2026-10-26T00:00:00"))
    assert (e["article"], e["date_debut"]) == (normaliser_numero(" l 211-1 "), "2026-10-26")
    assert e["texte_html"] == brut()["texte_html"]  # HTML d'origine, pas le texte converti


def test_doc_id_en_double_refuse(
    tmp_path,
): ...  # deux notices de même doc_id → ErreurEnvoi match le doc_id


def test_ecart_consigne_dans_le_manifeste(
    tmp_path,
): ...  # instantané avec un article vide → absent des entrées, présent dans ecarts


def test_sources_reelles_volumes_et_identite():
    jeu = agreger(dernier("code-assurances"), dernier("bareme"), NOTICES, PROCEDURES)
    assert jeu["manifeste"]["par_source"] == {"legifrance": 119, "redige": 4, "bareme": 6}
    assert jeu["manifeste"]["ecarts"] == []
    assert sum(e["etat"] == "ABROGE" for e in jeu["entrees"]) >= 11
    assert (
        ecrire_jeu(jeu, tmp_path).read_bytes() == VERSIONNE.read_bytes()
    )  # data/aggregated/corpus-2026-10-27.json
```

(`brut(**surcharges)` = un article Légifrance valide modifié champ par champ, comme `_brut` de `test_corpus.py`.)

- [ ] **Step 2: Run** `uv run pytest rag/tests/unit/test_agreger.py --no-cov -q` → FAIL (module absent).
- [ ] **Step 3: Implement** `cli/agreger.py` et la cible Makefile.
- [ ] **Step 4: Run** `make agreger` → `✔ data/aggregated/corpus-2026-10-27.json (129 entrées, 0 écarts)` ; relancer → `git status --porcelain data/aggregated` stable ; tests → PASS ; `make lint` → OK.
- [ ] **Step 5: Commit** `feat(rag): agrégation des sources en un jeu unique data/aggregated (#52)` (inclure le JSON).

---

### Task 5: Ingestion du jeu agrégé (`--jeu`)

**Files:**
- Modify: `rag/agentinsurflow_rag/cli/ingest.py`, `Makefile` (`ingest` : paramètre `JEU`)
- Test: `rag/tests/integration/test_cli_ingest.py` (ajouts ; adapter les tests qui ingèrent `procedures_internes` par `--source`)

**Interfaces:**
- Consumes: le fichier de Task 4.
- Produces:
  - `lire_jeu(chemin: Path) -> tuple[list[dict[str, Any]], str, Date]` : vérifie `sha_articles(entrees) == manifeste["sha256"]` sinon `ErreurEnvoi("jeu altéré : …")` ; date = `manifeste["date"]`.
  - `--jeu PATH` : exclusif avec `--instantane` et `--source` (`ErreurEnvoi`, code 1). Les entrées sont regroupées par `collection` (ordre de `COLLECTIONS`) ; chaque groupe part par `envoyer(...)` sans les clés `collection`/`source` ; une preuve par collection, nommage actuel (`ingestion-{prefixe}{date}-{env}.json`), `mode: "jeu"`.
  - `--collection procedures_internes --source …` → `ErreurEnvoi` : « les procédures internes sont générées : make agreger puis make ingest JEU=… ».
  - Makefile : `$(if $(JEU),--jeu $(JEU))` ; aide de la cible mise à jour.

- [ ] **Step 1: Write the failing tests** (avec le faux transport `appels` existant)
  - `test_jeu_envoie_chaque_collection_et_ecrit_ses_preuves` : jeu de 3 entrées (une par collection) → 3 `POST /api/ingestions` dont les corps ont `collection` = chacune des trois, articles sans clé `source` ; 3 preuves écrites.
  - `test_jeu_altere_refuse` : une entrée modifiée après écriture → code 1, message contient « altéré », aucun appel HTTP.
  - `test_jeu_exclusif_avec_instantane_et_source` (paramétré) → code 1, aucun appel.
  - `test_procedures_par_source_refusees` → code 1, message contient « make agreger ».
- [ ] **Step 2: Run** `uv run pytest rag/tests/integration/test_cli_ingest.py --no-cov -q` → les nouveaux échouent.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make test` → vert (ou, s'il exige la base, `uv run pytest rag/tests --no-cov -q`) ; `make lint` → OK. Si `docker`/compose est disponible : `make up`, puis `make ingest URL=http://localhost:8000 JEU=data/aggregated/corpus-2026-10-27.json` deux fois → la 2ᵉ donne « 0 insérés ».
- [ ] **Step 5: Commit** `feat(rag): make ingest JEU=… ingère le jeu agrégé, collection par collection (#52)`

---

### Task 6: Déploiement et documentation

**Files:**
- Modify: `.github/workflows/deploy.yml` (étape « Corpus », l. ~515-522)
- Modify: `docs/donnees/pipeline.md`, `docs/donnees/sources.md`, `rag/corpus/README.md`

- [ ] **Step 1: `deploy.yml`** — remplacer les trois `make ingest` par :

```bash
make install
make agreger
# régénéré = versionné : sinon le jeu ingéré ne serait pas celui du dépôt
git status --porcelain data/aggregated | grep . && { echo "::error::jeu agrégé non à jour : make bareme && make agreger"; exit 1; } || true
make ingest URL="$URL" JEU="$(ls data/aggregated/corpus-*.json | sort | tail -1)"
```

  Mettre à jour le commentaire de l'étape (jeu agrégé #52 au lieu de « instantané puis documents rédigés »).
- [ ] **Step 2: `pipeline.md`** — section « Agrégation (#52) » : spécifications techniques (entrées, sortie, schéma d'une entrée, manifeste), règles par source (Légifrance → `textes_reglementaires`, notices → `notices_produits`, barème + rédigés → `procedures_internes`), choix de nettoyage (corrompu = partiel, vide, < 20 caractères, date invalide ; abrogés gardés, filtrés par le serveur) et d'homogénéisation (dates ISO, numéros normalisés, état en majuscules, HTML/Markdown gardés tels quels car convertis par `html_vers_texte`), dépendances (aucune nouvelle), commandes (`make bareme`, `make agreger`, `make ingest JEU=…`), enchaînement (schéma barème → instantané → agrégation → ingestion), **modèle Merise inchangé** (`regle_id` déjà stocké, migration `0003_regle_id`).
- [ ] **Step 3: `sources.md`** — ajouter l'instantané du barème (origine `fonction-calcul`, JSON, données inventées, rôle : partie « Règle » des procédures, GF5) ; `rag/corpus/README.md` — les procédures sont la partie rédigée, l'en-tête et la règle sont générés, marqueur `{version_bareme}`.
- [ ] **Step 4: Verify** `make lint && make test` → vert ; `actionlint .github/workflows/deploy.yml` si installé.
- [ ] **Step 5: Commit** `docs(données): agrégation et barème citable ; deploy ingère le jeu agrégé (#52, #99)`

---

### Task 7: PR, release et production

- [ ] **Step 1:** Revue de branche (superpowers:requesting-code-review puis `ponytail-review`, synthèse des deux).
- [ ] **Step 2:** PR vers `main` : « Closes #99, Closes #52 », corps via la skill `pr-description`, cases des critères C3/C4 cochées avec le fichier qui les prouve. Attendre la CI verte.
- [ ] **Step 3 (confirmer avec l'utilisateur avant chaque action visible) :** fusion, release suivante (v0.6.25) selon le processus habituel du dépôt, suivi de `ci-cd.yml` → staging puis production.
- [ ] **Step 4: Verify en production** : version de la Function de calcul = tag (contrôle déjà dans `deploy.yml`) ; preuve `eval/preuves/ingestion-procedures_internes-*-production.json` : 6 insérés, 0 rejet ; `ingestion-*-production.json` (textes) : rejets = abrogés seulement ; un `/api/extraits` sur une question de suspension renvoie `PI-R01_SUSPENSION` avec `regle_id`.
