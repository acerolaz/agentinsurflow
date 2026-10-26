# RAG · notices_produits, procedures_internes et regle_id (#98) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** permettre au Rédacteur de produire une fiche réelle : le corpus contient des notices produits (GF6 sur ACCEPTE) et des procédures internes portant le `regle_id` du barème (GF5 sur REFUS), lisibles par le rôle `Gestionnaire` et renvoyées par `/api/extraits` donc par `search_rag`.

**Architecture:** on étend le service `rag` existant (hexagonal) sans nouvelle table : une colonne facultative `document.regle_id` (migration 0003), traversant `ArticleEntrant` → `ArticlePropre` → `PgDepotCorpus` → `CitationRag`/`CitationRagDTO`. Le cluster aplatit déjà `citation` dans ses `sources` (`fabrique._source`) et le serveur MCP relaie `/api/extraits` tel quel : **aucun changement hors de `rag/`, du `Makefile`, de `deploy.yml` et des docs**. Les documents rédigés sont des fichiers Markdown du dépôt, ingérés par la CLI existante avec `--collection` et `--source`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Core async, Alembic, pgvector, pytest, uv.

**Spec:** issue GitHub #98 + description validée en chat le 26/10 (résumée ci-dessous).

Décisions validées :
- notices rédigées par Claude, relues par Acerola ; une notice par formule, `doc_id` = valeur de la formule (`tiers`, `tous_risques`) ;
- `regle_id` porté par `procedures_internes`, une procédure par règle du barème (`R01_SUSPENSION` … `R06_JEUNE_PERMIS_PUISSANCE`, voir `fonction-calcul/agentinsurflow_calcul/domain/bareme.py`) ;
- source = Markdown du dépôt ; `tiers_etendu` hors périmètre (🔴 P13) ; `cgv_conditions` reste fermée.

## Global Constraints

- **Exploration par graphify d'abord** (demande d'Acerola) : avant d'ouvrir un fichier ou de chercher un symbole, `graphify query "<question>"` depuis `/Volumes/CodeSource/myRepos/simplon/certification` (graphe `graphify-out/`) ; `Read`/`grep` seulement pour lire la zone qu'on va modifier. Tout sous-agent d'exécution reçoit cette consigne dans son brief.
- Niveau de chaque test nommé avant écriture (`.claude/rules/testing-pyramid.md`) : Task 1 = TU ; Tasks 2-3 = TI (base, fichiers, HTTP en mémoire).
- Branche `feat/rag-notices` depuis `main` ; aucun changement de version de dépendance (aucune dépendance ajoutée : en-tête Markdown parsé en stdlib).
- `domain/` ne dépend que de la stdlib (vérifié par `rag/tests/unit/test_architecture.py`).
- Collections ingérables : exactement `textes_reglementaires`, `notices_produits`, `procedures_internes` ; toute autre → 422.
- `COLLECTIONS_PAR_ROLE` : `Gestionnaire` → les trois ; tout autre rôle → rien (OWASP API1, refus par défaut).
- `regle_id` facultatif, motif `^R\d{2}_[A-Z0-9_]+$`, 64 caractères au plus ; `null` pour les textes Légifrance.
- Les mentions Etalab (`/api/documents/{doc_id}/attribution`) ne concernent que `textes_reglementaires`.
- Rien d'écrit dans Azure depuis le poste : le déploiement passe par `deploy.yml`.

## Review Focus

1. **`regle_id` modifié sans changer le texte ni la version** : aujourd'hui le hash ne couvre que le texte → « inchangé », l'ancien `regle_id` resterait en base sans bruit. Attendu : le hash couvre aussi `regle_id` (inchangé quand il est absent, pour ne pas périmer les hash Légifrance), donc même version → `conflit_version` signalé. Test en Task 1.
2. **Attribution Etalab d'une notice** : `/attribution` sur `tiers` affirmerait « Légifrance, Licence Ouverte » pour un texte maison. Attendu : 404. Test en Task 2.
3. **Base `vecteurs` éphémère au déploiement** (`deploy.yml` : « chaque révision repart vide ») : sans ingestion des Markdown dans la CI, staging/production retombent en `REVUE_HUMAINE`. Attendu : `deploy.yml` ingère les deux dossiers après Légifrance. Couvert en Task 3.
4. **Collection inconnue ou `regle_id` mal formé** dans un lot : 422, rien d'écrit. Tests en Task 2.
5. **Rôle sans table** (ex. `Ingestion` seul) sur `/api/extraits` : 403 ou zéro collection, jamais une notice. Test en Task 2.

Hors périmètre, connu : un contrat en `tiers_etendu` n'a pas de notice → `REVUE_HUMAINE` (P13).

---

### Task 1: Domaine — `regle_id` dans l'article propre, collections par rôle

**Files:**
- Modify: `rag/agentinsurflow_rag/domain/models.py` (`ArticlePropre`, `CitationRag`)
- Modify: `rag/agentinsurflow_rag/domain/corpus.py` (`COLLECTIONS_PAR_ROLE`, `nettoyer`, constantes de collections)
- Test: `rag/tests/unit/test_corpus.py`

**Interfaces:**
- Produces:
  - `COLLECTION_S3 = "textes_reglementaires"`, `COLLECTION_NOTICES = "notices_produits"`, `COLLECTION_PROCEDURES = "procedures_internes"` dans `domain/corpus.py`
  - `COLLECTIONS_PAR_ROLE = {"Gestionnaire": (COLLECTION_S3, COLLECTION_NOTICES, COLLECTION_PROCEDURES)}`
  - `ArticlePropre.regle_id: str | None = None` (dernier champ, défaut `None`)
  - `CitationRag.regle_id: str | None = None` (dernier champ, défaut `None`)
  - `nettoyer(brut)` recopie `brut.get("regle_id")` (chaîne non vide, sinon `None`) ; `hash_contenu` = `hash_contenu(texte)` si `regle_id` est `None`, sinon `hash_contenu(f"{texte}\n{regle_id}")`

- [ ] **Step 1: Write the failing tests**

```python
def test_gestionnaire_lit_les_trois_collections() -> None:
    assert collections_pour(frozenset({"Gestionnaire"})) == [
        "notices_produits", "procedures_internes", "textes_reglementaires"
    ]

def test_role_absent_ne_lit_rien() -> None:
    assert collections_pour(frozenset({"Ingestion"})) == []

def test_nettoyer_recopie_regle_id() -> None:
    propre = nettoyer(article_valide() | {"regle_id": "R01_SUSPENSION"})
    assert isinstance(propre, ArticlePropre) and propre.regle_id == "R01_SUSPENSION"

def test_nettoyer_sans_regle_id_garde_le_hash_du_texte() -> None:
    propre = nettoyer(article_valide())
    assert propre.regle_id is None and propre.hash_contenu == hash_contenu(propre.texte)

def test_regle_id_change_le_hash() -> None:
    a, b = nettoyer(article_valide() | {"regle_id": "R01_SUSPENSION"}), nettoyer(article_valide() | {"regle_id": "R02_RESILIATIONS"})
    assert a.hash_contenu != b.hash_contenu
```
(`article_valide()` = le brut déjà utilisé par `test_nettoyer_article_valide` ; le factoriser s'il ne l'est pas.)

- [ ] **Step 2: Run** `uv run pytest rag/tests/unit/test_corpus.py -q --no-cov` — Expected: les 4 nouveaux tests échouent (`regle_id` absent, collections).
- [ ] **Step 3: Implement** les interfaces ci-dessus. `garde_fous.COLLECTION_NOTICES` du cluster a la même valeur : ne pas l'importer (services séparés).
- [ ] **Step 4: Run** `uv run pytest rag/tests/unit -q --no-cov` — Expected: PASS (dont `test_architecture.py`).
- [ ] **Step 5: Commit** `feat(rag): regle_id et collections notices/procédures dans le domaine (#98)`

### Task 2: Persistance et API — migration 0003, ingestion par collection, `regle_id` dans `/api/extraits`

**Files:**
- Create: `rag/migrations/vecteurs/versions/0003_regle_id.py` (sur le modèle de `0002_extrait_le.py`)
- Modify: `rag/agentinsurflow_rag/infrastructure/postgres/corpus.py` (`inserer`, `SQL_HYBRIDE`, `SQL_PAR_ARTICLES`)
- Modify: `rag/agentinsurflow_rag/api/schemas/corpus.py` (`ArticleEntrant`, `LotIngestion`, `CitationRagDTO`)
- Modify: `rag/agentinsurflow_rag/application/use_cases/consulter.py` (`attribuer`)
- Test: `rag/tests/integration/test_ingestions_api.py`, `test_extraits_api.py`, `test_attribution_api.py`, `test_migrations_vecteurs.py`

**Interfaces:**
- Consumes: Task 1 (`ArticlePropre.regle_id`, `CitationRag.regle_id`, constantes de collections).
- Produces:
  - migration `0003` : `ALTER TABLE document ADD COLUMN regle_id text` (nullable), downgrade = `DROP COLUMN`
  - `ArticleEntrant.regle_id: str | None = Field(default=None, pattern=r"^R\d{2}_[A-Z0-9_]+$", max_length=64, examples=["R01_SUSPENSION"])` ; **attention** : `extra="ignore"` et champs facultatifs → un motif invalide doit lever 422 sur le lot (Pydantic le fait), pas un rejet d'article
  - `LotIngestion.collection: Literal["textes_reglementaires", "notices_produits", "procedures_internes"]`
  - `CitationRagDTO.regle_id: str | None`
  - `SQL_HYBRIDE` et `SQL_PAR_ARTICLES` sélectionnent `d.regle_id` ; `inserer` l'écrit
  - `attribuer(...)` renvoie `None` (→ 404 existant) quand `document.collection != COLLECTION_S3`

- [ ] **Step 1: Write the failing tests** (style des fichiers existants, fixtures `api`/`corpus`, `entetes(...)`, `corpus_de_test.article(...)`)

```python
# test_ingestions_api.py
async def test_ingestion_notice_puis_extrait_avec_collection(api) -> None:
    # lot collection="notices_produits", article doc_id="tiers", article="NP-TIERS",
    # url_source="https://github.com/acerolaz/agentinsurflow/blob/main/rag/corpus/notices_produits/tiers.md"
    # → 201 ; GET /api/extraits (Gestionnaire) sur une question du texte : un résultat
    # avec citation.collection == "notices_produits" et citation.doc_id == "tiers"

async def test_regle_id_aller_retour(api) -> None:
    # lot procedures_internes, regle_id="R01_SUSPENSION" → /api/extraits
    # → citation["regle_id"] == "R01_SUSPENSION"

async def test_texte_legifrance_regle_id_null(corpus) -> None:
    # extrait du corpus de fixture → citation["regle_id"] is None

@pytest.mark.parametrize("corps", [collection inconnue "cgv_conditions", collection "inexistante",
                                   regle_id "r01", regle_id "R1_X"])
async def test_lot_invalide_422_rien_d_ecrit(api, conn_writer, corps) -> None: ...

async def test_meme_version_regle_id_change_conflit(api) -> None:
    # même doc_id, même version, même texte, regle_id R01 puis R02 → second rapport : rejet "conflit_version"

# test_extraits_api.py
async def test_role_ingestion_seul_ne_lit_pas_les_notices(api) -> None:
    # notice ingérée ; GET /api/extraits avec entetes("Ingestion") → 403

# test_attribution_api.py
async def test_attribution_d_une_notice_404(api) -> None:
    # notice "tiers" ingérée ; GET /api/documents/tiers/attribution (Gestionnaire) → 404

# test_migrations_vecteurs.py
def test_0003_ajoute_regle_id_nullable(...) -> None:  # suivre le test existant de 0002 (upgrade/downgrade)
```

- [ ] **Step 2: Run** `make test-integration` (ou `uv run pytest rag/tests/integration -q` avec le PostgreSQL du compose) — Expected: les nouveaux tests échouent.
- [ ] **Step 3: Implement** les interfaces ci-dessus.
- [ ] **Step 4: Run** `make test-integration` — Expected: PASS, couverture ≥ 80 %, aucun test existant cassé (notamment `test_questions_demo.py` et `test_reponses_api.py`, qui voient maintenant trois collections).
- [ ] **Step 5: Commit** `feat(rag): ingestion par collection et regle_id renvoyé par /api/extraits (#98)`

### Task 3: CLI `--collection --source`, Makefile, déploiement

**Files:**
- Modify: `rag/agentinsurflow_rag/cli/ingest.py`
- Modify: `Makefile` (cible `ingest`)
- Modify: `.github/workflows/deploy.yml` (étape « Corpus », ~l. 455)
- Test: `rag/tests/integration/test_cli_ingest.py`

**Interfaces:**
- Consumes: Task 2 (l'API accepte les trois collections et `regle_id`).
- Produces:
  - `lire_markdown(dossier: Path, collection: str) -> list[dict[str, Any]]` : un article par `*.md`, triés par nom. En-tête entre deux lignes `---`, lignes `cle: valeur` (stdlib, pas de YAML) avec `doc_id`, `version`, `article`, `date_debut`, `regle_id` (facultatif). Corps → `texte_html` tel quel (`html_vers_texte` garde les lignes). `etat = "VIGUEUR"`. `url_source = f"https://github.com/acerolaz/agentinsurflow/blob/main/rag/corpus/{collection}/{fichier.name}"`. En-tête absent ou champ obligatoire manquant → `ErreurEnvoi` avec le nom du fichier.
  - `envoyer(..., collection: str = "textes_reglementaires")` met `collection` dans le corps du lot.
  - arguments `--collection` (défaut `textes_reglementaires`, choix = les trois) et `--source DIR` ; `--source` sans `--collection` autre que `textes_reglementaires` (ou l'inverse) → code 1 avec message clair. Avec `--source` : `sha = sha_articles(articles)`, date = `--date`, mode `"markdown"`, preuve `ingestion-{collection}-{date}-{env}.json`.
  - Makefile : `make ingest [URL=…] [INSTANTANE=…] [COLLECTION=… SOURCE=…]`.
  - `deploy.yml` : après la ligne Légifrance,
    `make ingest URL="$URL" COLLECTION=notices_produits SOURCE=rag/corpus/notices_produits`
    `make ingest URL="$URL" COLLECTION=procedures_internes SOURCE=rag/corpus/procedures_internes`

- [ ] **Step 1: Write the failing tests** (`tmp_path`, transport httpx simulé comme `test_rejeu_instantane_n_appelle_pas_piste`)

```python
def test_lire_markdown_en_tete_et_corps(tmp_path) -> None:
    # tiers.md avec doc_id: tiers / version: tiers-v1 / article: NP-TIERS / date_debut: 2026-10-26
    articles = lire_markdown(tmp_path, "notices_produits")
    assert articles[0]["doc_id"] == "tiers" and articles[0]["etat"] == "VIGUEUR"
    assert articles[0]["url_source"].endswith("/rag/corpus/notices_produits/tiers.md")
    assert "regle_id" not in articles[0] or articles[0]["regle_id"] is None

def test_lire_markdown_regle_id(tmp_path) -> None: ...  # regle_id: R01_SUSPENSION recopié
def test_markdown_sans_en_tete_code_1(tmp_path, capsys) -> None: ...  # message cite le fichier
def test_source_envoie_la_collection(tmp_path, appels) -> None:
    # main(["--collection", "procedures_internes", "--source", str(tmp_path), ...]) == 0
    # json du POST : corps["collection"] == "procedures_internes"
def test_source_sans_collection_code_1(tmp_path, capsys) -> None: ...
```

- [ ] **Step 2: Run** `uv run pytest rag/tests/integration/test_cli_ingest.py -q --no-cov` — Expected: FAIL.
- [ ] **Step 3: Implement** ; mettre à jour la docstring du module (usage `--source`).
- [ ] **Step 4: Run** le même fichier — Expected: PASS ; `make lint` propre.
- [ ] **Step 5: Commit** `feat(rag): make ingest --collection/--source pour les documents rédigés, ingérés au déploiement (#98)`

### Task 4: Contenu — notices produits et procédures internes

Acerola n'est pas expert réglementaire : Claude rédige, Acerola relit le sens métier, pas le droit.

**Files:**
- Create: `rag/corpus/notices_produits/tiers.md`, `rag/corpus/notices_produits/tous_risques.md`
- Create: `rag/corpus/procedures_internes/R01_SUSPENSION.md` … `R06_JEUNE_PERMIS_PUISSANCE.md` (6 fichiers)
- Create: `rag/corpus/README.md` (5 lignes : textes fictifs rédigés pour le projet, droits détenus par le projet, format d'en-tête, commande d'ingestion)

**Interfaces:**
- Consumes: le format d'en-tête de Task 3.
- Contenu attendu :
  - **Notice** (≈ 300–500 mots, au moins 20 caractères de texte) : `doc_id` = formule, `article` = `NP-TIERS` / `NP-TOUS-RISQUES`, `version` = `<doc_id>-v1`. Sections : objet, garanties (RC obligatoire L211-1 pour les deux ; dommages tous accidents, vol, incendie, bris de glace pour tous risques), plafonds, franchises, exclusions, renvoi au coefficient bonus-malus (A121-1). Mention « document fictif ».
  - **Procédure** : `doc_id` = `PI-<regle_id>`, `article` = `PI-<regle_id>` avec `_` remplacé par `-`, `regle_id` = la règle. Sections : règle (condition et motif repris **mot pour mot** de `bareme.py`), décision (refus, sous réserve de validation du gestionnaire), pièces à vérifier, fondement (articles du Code des assurances déjà présents dans `data/raw/code-assurances-*.json`, cités par leur numéro : seulement des numéros qu'on y trouve).
  - Les numéros d'articles cités sont vérifiés dans l'instantané ; aucun numéro inventé.

- [ ] **Step 1: Rédiger** les 8 fichiers et le README.
- [ ] **Step 2: Vérifier les citations** : chaque numéro d'article cité figure dans le dernier `data/raw/code-assurances-*.json` (`grep`), chaque `regle_id` figure dans `bareme.py`.
- [ ] **Step 3: Vérifier le format** : `uv run python -c "from pathlib import Path; from agentinsurflow_rag.cli.ingest import lire_markdown; [print(len(lire_markdown(Path(f'rag/corpus/{c}'), c))) for c in ('notices_produits','procedures_internes')]"` — Expected: `2` puis `6`.
- [ ] **Step 4: Ingestion locale** (`make up` puis `make ingest` ×3 comme dans `deploy.yml`) et `GET /api/extraits?question=garanties de la formule tous risques` → au moins un extrait `notices_produits`, `doc_id == "tous_risques"`.
- [ ] **Step 5: Commit** `docs(rag): notices produits et procédures internes rédigées pour le projet (#98)` — **puis faire relire à Acerola avant la PR.**

### Task 5: Documentation, OpenAPI, vérification complète

**Files:**
- Modify: `docs/donnees/modele.md` (ligne `document` : colonne `regle_id` text NULL ; collections ingérables)
- Modify: `docs/donnees/sources.md` (nouvelle source : documents rédigés pour le projet, `rag/corpus/`)
- Regenerate: `docs/openapi/rag.json` via `make openapi`

- [ ] **Step 1:** mettre à jour les deux docs ; `make openapi` ; vérifier que `rag.json` contient `regle_id` et les trois valeurs de `collection`.
- [ ] **Step 2: Run** `make test && make test-integration && make lint` — Expected: tout PASS, couverture ≥ 80 %.
- [ ] **Step 3: Commit** `docs(rag): modèle, sources et OpenAPI pour notices, procédures et regle_id (#98)`
- [ ] **Step 4:** PR vers `main` (`Closes #98`), critères C4/C5 cochés. Après déploiement staging : l'E2E depuis le poste (`project-e2e-staging-poste`) doit voir `test_dossier_complet_en_analyse_puis_revue` sortir de `REVUE_HUMAINE`, ou sinon la cause est dans #45/#99.
