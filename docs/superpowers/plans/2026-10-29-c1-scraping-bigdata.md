# C1 / C2 — scraping des notices et big data PySpark : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** ajouter les deux sources de collecte qui manquent au référentiel. La première est le scraping des notices produits, publiées par la gateway (#45). La seconde est un fichier tabulaire et un système big data : freMTPL2 lu par PySpark en local et interrogé en Spark SQL (#51). Chacune produit un instantané versionné avec son manifeste SHA-256.

**Architecture :** la gateway sert des pages HTML statiques sous `/notices/` et un `/robots.txt`. `tools/scraping_notices.py` les collecte et écrit `data/raw/notices-<date>.json` au format des instantanés Légifrance (`sauvegarder_instantane`). `ingest` rejoue ce fichier dans `notices_produits`. `tools/extraction_bigdata.py` réutilise le téléchargement figé de freMTPL2 (`fonction-calcul/entrainement/donnees.py`), convertit les fichiers ARFF en Parquet et exécute des requêtes Spark SQL. Il écrit `data/raw/fremtpl2-agregats-<date>.json`. Le travail tient en deux PR : PR 1 = tâches 1 à 7, PR 2 = tâche 8 (après le déploiement de la PR 1 en prod).

**Tech Stack :** ASP.NET Core (gateway, xUnit + `WebApplicationFactory`), Python 3.12, `httpx`, `html.parser` et `urllib.robotparser` (bibliothèque standard), PySpark 4 (groupe uv `bigdata`), OpenJDK 17.

**Spec :** `docs/superpowers/specs/2026-10-29-c1-scraping-bigdata-design.md`

## Global Constraints

- Français partout : code métier, tests, docs, messages de commit.
- Aucune version de projet relevée (`pyproject.toml` racine reste en `0.6.0`, `rag/pyproject.toml` inchangé).
- Aucune nouvelle dépendance hors `pyspark` (groupe `bigdata`, jamais dans `dev` ni dans un paquet du workspace).
- `doc_id` des notices inchangés : `tiers`, `tiers_etendu`, `tous_risques`, `jeunes_conducteurs`. Les `version`, `article` et `date_debut` sont copiés tels quels des en-têtes Markdown actuels.
- `/notices/` et `/robots.txt` sont publics, en lecture seule, servis **avant** `UseAuthentication`. Aucune politique existante n'est affaiblie.
- Les données brutes freMTPL2 (ARFF, Parquet) ne sont jamais commitées. Elles restent dans le cache `FREMTPL2_CACHE` (défaut `/tmp/fremtpl2-cache`).
- freMTPL2sev : `https://openml.org/data/v1/download/20649149/freMTPL2sev.arff`, OpenML 41215, version 1, CC0, SHA-256 `047632016b87e132247124f449a95d6d0e9f8ba05f2fe0947ef76ab8aaa10e0a`, MD5 OpenML `24cc74449e3931cb1aad0d43a12e7a6e`, 26 639 lignes de données (mesuré le 29/10).
- Branche : une PR en brouillon par étape, jamais de push sur `main`. Écritures Azure : aucune.
- Python : `ruff` (longueur de ligne 100) et `mypy --strict` sur `tools/` (`make lint`).

## Review Focus

1. **Le robots.txt interdit `/notices/`** (règle modifiée par erreur) : le script refuse de collecter, sort en code 1 et n'écrit aucun instantané. Testé en tâche 3.
2. **Une page de notice sans `<meta name="doc_id">`** (ou avec une méta vide) : `ErreurScraping` nomme l'URL fautive, aucun instantané partiel n'est écrit. Testé en tâche 3.
3. **Un instantané de notices rejoué sans `COLLECTION`** : il partirait dans `textes_reglementaires` et GF6 casserait. `ingest` refuse quand le `perimetre` du manifeste désigne une autre collection. Testé en tâche 2.
4. **Des lignes freMTPL2 hors bornes** (`Exposure` ≤ 0 ou > 1, `BonusMalus` hors 50–230) et **des sinistres sans contrat** dans freq : ils sont exclus des agrégats, pas comptés. Testé en tâche 5.
5. **Java absent** au moment de lancer `make bigdata` : message clair (« Java 17 requis… ») et code 1, pas de trace Py4J. Testé en tâche 5.

---

### Task 1 : pages des notices et robots.txt servis par la gateway

**Files :**
- Create : `gateway/src/AgentInsurFlow.Gateway.Api/wwwroot/notices/index.html`, `conditions.html`, `tiers.html`, `tiers_etendu.html`, `tous_risques.html`, `jeunes_conducteurs.html`
- Modify : `gateway/src/AgentInsurFlow.Gateway.Api/Program.cs:252-264` (après le bloc de l'espace, avant `UseSwaggerUI`)
- Test : `gateway/tests/AgentInsurFlow.Gateway.Api.Tests/NoticesTests.cs`

**Interfaces :**
- Produces (contrat HTML lu par la tâche 3) :
  - chaque page de notice a dans `<head>` les balises `<meta name="doc_id" content="…">`, `<meta name="version" …>`, `<meta name="article" …>` et `<meta name="date_debut" …>`. Le corps de la notice est dans un seul `<main>`, avec uniquement `h1`, `h2`, `p`, `ul`/`li`. Le pied de page contient `<a href="conditions.html">` ;
  - `index.html` liste les notices par `<a class="notice" href="<doc_id>.html">` ;
  - `GET /robots.txt` renvoie `text/plain` avec exactement :
    ```
    User-agent: *
    Allow: /notices/
    Disallow: /
    ```

- [ ] **Step 1 : écrire les tests qui échouent** (`NoticesTests`, même fixture `Backends` et même style qu'`EspaceTests`)
  - `Index_servi_sans_jeton_avec_csp` : `GET /notices/` répond 200 en `text/html`. La CSP contient `default-src 'none'` et `frame-ancestors 'none'`.
  - `Notice_tiers_porte_ses_metadonnees` : `GET /notices/tiers.html` répond 200, et le corps contient `<meta name="doc_id" content="tiers">`.
  - `Robots_txt_autorise_notices_seulement` : `GET /robots.txt` répond 200 en `text/plain`, et le corps est égal au texte ci-dessus (fins de ligne `\n`).
  - `Api_reste_protegee` : `GET /api/documents` sans jeton répond toujours 401.

- [ ] **Step 2 : lancer les tests et vérifier l'échec** : `make gateway-test` → les 3 premiers tests échouent (404).

- [ ] **Step 3 : écrire les 6 pages.** Elles sont converties à la main depuis `rag/corpus/notices_produits/*.md` : même texte, les titres `#` et `##` deviennent `h1` et `h2`, les listes `-` deviennent `ul`/`li`. Ni JS, ni CSS, ni style en ligne. `conditions.html` dit que les documents sont fictifs, rédigés pour AgentInsurFlow, que le projet en détient les droits, qu'ils sont réutilisables uniquement dans le cadre du projet, et qu'aucune donnée personnelle n'y figure.

- [ ] **Step 4 : servir les fichiers dans `Program.cs`.** Deuxième couple `UseDefaultFiles` / `UseStaticFiles` sur `wwwroot/notices` avec `RequestPath = "/notices"` et `const string CspNotices = "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"`. Ajouter aussi `app.MapGet("/robots.txt", …)` qui renvoie `Results.Text(…, "text/plain")`, avec `.AllowAnonymous().DisableRateLimiting().ExcludeFromDescription()`.

- [ ] **Step 5 : lancer les tests et vérifier qu'ils passent** : `make gateway-test` → tous verts, y compris `AutorisationTests.Toutes_les_routes_declarent_une_politique`.

- [ ] **Step 6 : commit** — `feat(gateway): notices produits publiques sous /notices/ et robots.txt (#45)`

### Task 2 : `ingest` sait rejouer un instantané de notices

**Files :**
- Modify : `rag/agentinsurflow_rag/cli/ingest.py:1-14` (docstring), `:73-91` (`sauvegarder_instantane`), `:246-251` (`_instantane`)
- Modify : `Makefile:43-44` (cible `ingest`)
- Test : `rag/tests/integration/test_cli_ingest.py`

**Interfaces :**
- Produces : `sauvegarder_instantane(articles: list[dict[str, Any]], dossier: Path, environnement: str, date: str, prefixe: str = "code-assurances", perimetre: str = PERIMETRE.pattern) -> Path` écrit `<dossier>/<prefixe>-<date>.json`, avec `manifeste.perimetre = perimetre`. Les appels existants ne changent pas.
- Produces : `make ingest URL=… INSTANTANE=data/raw/notices-<date>.json COLLECTION=notices_produits`.

- [ ] **Step 1 : écrire les tests qui échouent**
  - `test_instantane_prefixe_et_perimetre` : `sauvegarder_instantane(CORPUS, tmp_path, "local", "2026-10-29", prefixe="notices", perimetre="notices_produits")` donne un chemin dont le nom est `notices-2026-10-29.json`, et un manifeste avec `perimetre == "notices_produits"`.
  - `test_rejeu_instantane_notices_dans_sa_collection` : `main(["--instantane", chemin, "--collection", "notices_produits", "--url", "http://gw", …])` renvoie 0. Le premier lot envoyé (`appels[0]`) porte `"collection": "notices_produits"`.
  - `test_instantane_notices_refuse_dans_une_autre_collection` : le même instantané passé sans `--collection` fait renvoyer 1 à `main`, avec un message qui contient `notices_produits`.
  - `test_source_et_instantane_exclusifs` : `--source` et `--instantane` ensemble font renvoyer 1 à `main`.

- [ ] **Step 2 : lancer les tests et vérifier l'échec** : `uv run pytest rag/tests/integration/test_cli_ingest.py -k "prefixe or notices or exclusifs" --no-cov` → FAIL.

- [ ] **Step 3 : implémenter.** Ajouter les deux paramètres à `sauvegarder_instantane`. Réécrire le contrôle d'entrée de `_instantane` :
  - erreur si `--source` et `--instantane` sont donnés ensemble ;
  - erreur si `--source` est donné avec `textes_reglementaires` (message actuel conservé) ;
  - erreur si aucun des deux n'est donné pour une autre collection.
  
  Quand `--instantane` est donné, lire `manifeste.perimetre`. S'il vaut un nom de `COLLECTIONS` différent de `args.collection`, lever `ErreurEnvoi(f"instantané de {perimetre}, pas de {args.collection}")`. Dans le `Makefile`, `--collection $(COLLECTION)` est passé dès que `COLLECTION` est défini, indépendamment de `SOURCE`. Mettre à jour la docstring.

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent** : `uv run pytest rag/tests/integration/test_cli_ingest.py --no-cov` → tous verts (les tests Markdown existants aussi).

- [ ] **Step 5 : commit** — `feat(ingest): rejeu d'un instantané de notices dans notices_produits (#45)`

### Task 3 : `tools/scraping_notices.py`

**Files :**
- Create : `tools/scraping_notices.py`
- Modify : `Makefile` (cible `scraper` et entrée `.PHONY`)
- Test : `tests/unit/test_scraping_notices.py`

**Interfaces :**
- Consumes : le contrat HTML de la tâche 1 ; `sauvegarder_instantane(..., prefixe="notices", perimetre="notices_produits")` et `sha_articles` de la tâche 2.
- Produces :
  - `AGENT = "AgentInsurFlow-scraping/1.0 (+https://github.com/acerolaz/agentinsurflow)"`, `NOTICES_REQUISES = ("tiers", "tiers_etendu", "tous_risques")`, `DELAI_S = 1.0`
  - `class ErreurScraping(Exception)`
  - `liens_notices(html: str, base: str) -> list[str]` : les URL absolues des `a.notice` de l'index, dans l'ordre.
  - `extraire_notice(html: str, url: str) -> dict[str, Any]` : un article au format de `lire_markdown` (`doc_id`, `version`, `article`, `date_debut`, `regle_id=None`, `etat="VIGUEUR"`, `texte_html`, `url_source=url`). Dans `texte_html`, chaque `h1`, `h2` et `li` est rendu en `# `, `## ` et `- `, chaque `p` en une ligne, avec une ligne vide avant chaque titre.
  - `collecter(client: httpx.Client, base: str, delai_s: float = DELAI_S) -> list[dict[str, Any]]` : lit robots.txt, l'index, puis chaque notice. Lève `ErreurScraping` si une URL est interdite, si un statut n'est pas 200, si une méta manque ou si une notice de `NOTICES_REQUISES` est absente. Les articles sont triés par `doc_id`.
  - `main(argv: Sequence[str] | None = None) -> int` : arguments `--url` (obligatoire), `--sortie` (défaut `data/raw`), `--date` (défaut aujourd'hui). Code 0 si tout va bien, 1 sur `ErreurScraping` ou `httpx.HTTPError`, avec un message sur stderr. Il affiche `✔ instantané <chemin> (<n> notices)`.
- `make scraper URL=<gateway>` → `uv run python tools/scraping_notices.py --url $(URL)`

- [ ] **Step 1 : écrire les tests qui échouent.** Un `httpx.MockTransport` sert `/robots.txt` et les fichiers **réels** de `gateway/.../wwwroot/notices/`.
  - `test_extraire_notice_tiers` : sur `tiers.html`, on obtient `doc_id == "tiers"`, `version == "tiers-2026.10-v1"`, `article == "NP-TIERS"` ; `"## Garanties" in texte_html` et `"- Responsabilité civile" in texte_html`.
  - `test_liens_index` : `liens_notices(index, "http://gw/notices/")` donne 4 URL, dont `http://gw/notices/tiers.html`.
  - `test_collecter_les_trois_formules` : l'ensemble des `doc_id` collectés contient `NOTICES_REQUISES`, et chaque `url_source` commence par `http://gw/notices/`. Les requêtes portent le User-Agent `AGENT`.
  - `test_robots_interdit_notices` : robots `Disallow: /` seul fait lever `ErreurScraping` par `collecter`, et `main` renvoie 1 sans écrire de fichier.
  - `test_notice_sans_doc_id` : une page sans méta `doc_id` fait lever `ErreurScraping`, avec l'URL dans le message.
  - `test_formule_manquante` : un index sans `tous_risques` fait lever `ErreurScraping` avec `tous_risques` dans le message.
  - `test_main_ecrit_instantane_et_manifeste` : `main` renvoie 0 et écrit `notices-<date>.json`, avec `manifeste.articles == 4`, `manifeste.perimetre == "notices_produits"`, et une SHA-256 égale à `sha_articles(articles)`.

  Le délai est passé à `0` dans les tests.

- [ ] **Step 2 : lancer les tests et vérifier l'échec** : `uv run pytest tests/unit/test_scraping_notices.py --no-cov` → ImportError.

- [ ] **Step 3 : implémenter `tools/scraping_notices.py`.** Une fonction par partie exigée : lancement (`main`), initialisation (client `httpx` avec `headers={"User-Agent": AGENT}`, `RobotFileParser.parse`), traitement (`collecter`, `extraire_notice` sur un `HTMLParser` de la bibliothèque standard), erreurs, fin (résumé), sauvegarde (`sauvegarder_instantane`). Ajouter la cible `scraper` au `Makefile`.

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent** : `uv run pytest tests/unit/test_scraping_notices.py --no-cov` → PASS ; `make lint` → OK.

- [ ] **Step 5 : vérifier contre la gateway locale.** Lancer `make up` puis `make scraper URL=http://localhost:8000` : la sortie affiche `✔ … (4 notices)`. **Supprimer** ce fichier local : seul l'instantané de prod (tâche 8) sera versionné.

- [ ] **Step 6 : commit** — `feat(collecte): scraping des notices produits publiées par la gateway (#45)`

### Task 4 : Java, PySpark et source freMTPL2sev

**Files :**
- Modify : `pyproject.toml` (groupe `[dependency-groups] bigdata = ["pyspark>=4.0,<5"]` ; override mypy `module = ["pyspark.*"]` `ignore_missing_imports = true`), `uv.lock`
- Modify : `fonction-calcul/entrainement/donnees.toml` (bloc `[source_sev]`), `fonction-calcul/entrainement/donnees.py:15-19,36-56`
- Test : `fonction-calcul/tests/unit/test_donnees_glm.py`

**Interfaces :**
- Produces : `SOURCE_SEV: dict[str, Any]` ; `telecharger(cache: Path, source: dict[str, Any] = _SOURCE) -> Path` (le comportement par défaut ne change pas) ; `attributs(fichier: Path) -> list[str]`, qui donne les noms des lignes `@attribute` jusqu'à `@data`, et que `charger()` réutilise.

- [ ] **Step 1 : installer Java** (accord d'Acerola du 29/10) : `brew install openjdk@17`. Vérifier avec `$(brew --prefix openjdk@17)/bin/java -version`, qui doit afficher `17.`. Ne pas créer de lien symbolique système : `make bigdata` (tâche 5) pose `JAVA_HOME` lui-même s'il est vide.

- [ ] **Step 2 : écrire les tests qui échouent**
  - `test_source_sev_figee` : `SOURCE_SEV["sha256"] == "0476…0e0a"` (valeur complète des contraintes globales), `SOURCE_SEV["openml_data_id"] == 41215`, `SOURCE_SEV["licence"] == "CC0"`.
  - `test_attributs_arff` : sur un ARFF minimal écrit dans `tmp_path` (`@relation x`, deux `@attribute`, `@data`, une ligne), on obtient `["IDpol", "ClaimAmount"]`.

- [ ] **Step 3 : lancer les tests et vérifier l'échec** : `uv run pytest fonction-calcul/tests/unit/test_donnees_glm.py --no-cov` → FAIL.

- [ ] **Step 4 : implémenter.** Ajouter le bloc `[source_sev]` (mêmes clés que `[source]`, avec les valeurs des contraintes globales et `lignes = 26639`). Ajouter `SOURCE_SEV`, puis le paramètre `source` de `telecharger`, qui lit `source["url"]`, `source["fichier"]` et `source["sha256"]`. Extraire `attributs()` de `charger()`. Ajouter le groupe `bigdata` et l'override mypy, puis lancer `uv lock`.

- [ ] **Step 5 : lancer les tests et vérifier qu'ils passent** : `uv run pytest fonction-calcul/tests/unit --no-cov` → PASS (GLM inchangé) ; `make lint` → OK ; `uv sync --group bigdata` installe pyspark.

- [ ] **Step 6 : commit** — `feat(donnees): source freMTPL2sev figée et groupe uv bigdata (#51)`

### Task 5 : `tools/extraction_bigdata.py`

**Files :**
- Create : `tools/extraction_bigdata.py`
- Modify : `Makefile` (cible `bigdata` et entrée `.PHONY`)
- Test : `tests/unit/test_extraction_bigdata.py`

**Interfaces :**
- Consumes : `telecharger`, `SOURCE_SEV`, `attributs` (tâche 4) ; `sauvegarder_instantane` (tâche 2).
- Produces :
  - `class ErreurBigData(Exception)`
  - `session_spark() -> SparkSession` : `local[*]`, `appName("agentinsurflow-bigdata")`. Elle lève `ErreurBigData("Java 17 requis : brew install openjdk@17")` si `shutil.which("java")` et `JAVA_HOME` sont tous deux absents.
  - `vers_parquet(spark: SparkSession, arff: Path, parquet: Path) -> None` : `spark.read.csv(str(arff), comment="@", quote="'", inferSchema=True).toDF(*attributs(arff))`, écrit en Parquet (`mode("overwrite")`).
  - `REQUETES: dict[str, str]`, deux requêtes Spark SQL sur les vues `freq` et `sev` :
    - `frequence_par_region` : sur `freq`, filtre `Exposure > 0 AND Exposure <= 1 AND BonusMalus BETWEEN 50 AND 230`. Colonnes `Region`, `contrats` (COUNT), `exposition` (SUM Exposure), `sinistres` (SUM ClaimNb), `frequence` (sinistres / exposition), triées par `Region`.
    - `cout_moyen_par_bonus_malus` : CTE `couts` = `sev` agrégé par `IDpol` (`montant` = SUM ClaimAmount, `nb` = COUNT), puis `/*+ BROADCAST(couts) */` et une **jointure interne** `freq.IDpol = couts.IDpol`, avec le même filtre que ci-dessus. Le résultat est groupé par `tranche_bm` (`CASE` : `50-99`, `100-149`, `150-230`), avec les colonnes `contrats_sinistres` (COUNT DISTINCT IDpol) et `cout_moyen` (SUM montant / SUM nb), triées par `tranche_bm`.
  - `executer(spark: SparkSession, parquet_freq: Path, parquet_sev: Path) -> list[dict[str, Any]]` : enregistre les vues, exécute `REQUETES` dans l'ordre et donne une ligne par résultat, de la forme `{"requete": nom, **ligne}`.
  - `main(argv: Sequence[str] | None = None) -> int` : arguments `--cache` (défaut `FREMTPL2_CACHE` ou `/tmp/fremtpl2-cache`), `--sortie` (défaut `data/raw`), `--date`, `--expliquer` (affiche `spark.sql(q).explain("formatted")` pour chaque requête). Il sauvegarde par `sauvegarder_instantane(lignes, sortie, "local", date, prefixe="fremtpl2-agregats", perimetre="freMTPL2freq×freMTPL2sev (OpenML 41214, 41215)")` et arrête toujours la session dans un `finally`. Code 1 sur `ErreurBigData`, `ValueError` (SHA-256) ou `OSError`.
- `make bigdata [ARGS=--expliquer]` → `JAVA_HOME=$${JAVA_HOME:-$$(brew --prefix openjdk@17 2>/dev/null)} PYTHONPATH=fonction-calcul uv run --group bigdata python tools/extraction_bigdata.py $(ARGS)`

- [ ] **Step 1 : écrire les tests qui échouent.** Le module commence par `pytest.importorskip("pyspark")` et saute aussi les tests si Java est introuvable : la CI n'installe pas le groupe `bigdata`. Une fixture `spark` est partagée au niveau du module.
  - `test_vers_parquet_lit_l_arff` : un ARFF sev de 3 lignes écrit dans `tmp_path`, puis converti, se relit avec 3 lignes et les colonnes `["IDpol", "ClaimAmount"]`.
  - `test_frequence_par_region_filtre_les_bornes` : freq contient 4 contrats en `R11`, dont un avec `Exposure = 0` et un avec `BonusMalus = 300`. On obtient une ligne `R11` avec `contrats == 2`.
  - `test_jointure_ignore_les_sinistres_sans_contrat` : sev contient un `IDpol` absent de freq. Il n'apparaît dans aucune tranche, et `cout_moyen` est égal à la valeur calculée à la main.
  - `test_main_sans_java` : avec `shutil.which` patché à `None` et `JAVA_HOME` retiré, `main` renvoie 1 et stderr contient `Java 17 requis`.

- [ ] **Step 2 : lancer les tests et vérifier l'échec** : `JAVA_HOME=$(brew --prefix openjdk@17) uv run --group bigdata pytest tests/unit/test_extraction_bigdata.py --no-cov` → ImportError.

- [ ] **Step 3 : implémenter** `tools/extraction_bigdata.py`. Même découpage en six parties que la tâche 3 ; ajouter la cible `bigdata` au `Makefile`.

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent** : la même commande → PASS. `make test` (sans le groupe) → les tests Spark sont **sautés**, le reste passe. `make lint` → OK.

- [ ] **Step 5 : commit** — `feat(collecte): extraction big data freMTPL2 en PySpark et Spark SQL (#51)`

### Task 6 : instantané big data et documentation C2

**Files :**
- Create : `data/raw/fremtpl2-agregats-<date>.json`
- Modify : `docs/donnees/requetes-sql.md` (nouvelle section « Spark SQL (big data) »)

- [ ] **Step 1 : produire l'instantané** : `make bigdata`. Attendu : `✔ instantané data/raw/fremtpl2-agregats-<date>.json`, dont le manifeste a une `sha256` non vide. Le fichier ne contient que des agrégats (22 régions + 3 tranches, soit 25 lignes).
- [ ] **Step 2 : capturer les plans** : `make bigdata ARGS=--expliquer`. Relever dans la sortie `ReadSchema` (élagage de colonnes), `PushedFilters` (filtres poussés à la lecture Parquet) et `BroadcastHashJoin` (diffusion de `couts`).
- [ ] **Step 3 : rédiger la section.** Pour chaque requête : l'objectif de collecte, les sélections, les filtres et leurs bornes (avec leur origine, `donnees.py`), les conditions, la jointure et son type (interne, pourquoi), et les optimisations, chacune justifiée par un extrait du plan. Ajouter le format colonne Parquet et la conversion une seule fois dans le cache.
- [ ] **Step 4 : vérifier** : `uv run python -c "import json; d=json.load(open('data/raw/fremtpl2-agregats-<date>.json')); print(d['manifeste'])"` affiche `articles == 25`.
- [ ] **Step 5 : commit** — `docs(donnees): requêtes Spark SQL documentées et instantané des agrégats (#51)`

### Task 7 : inventaire des sources et pipeline

**Files :**
- Modify : `docs/donnees/sources.md`, `docs/donnees/pipeline.md`

- [ ] **Step 1 : `sources.md`.**
  - Ajouter deux colonnes, **Pages notices (scraping)** et **freMTPL2 (fichier + big data)**, avec les mêmes lignes que les colonnes existantes. Il faut y mettre l'origine, le contenu, le format, la licence (projet / CC0), les données personnelles (aucune / anonymes), les **contraintes appliquées** (robots.txt lu et respecté, User-Agent, délai de 1 s, conditions de réutilisation ; SHA-256 figées, Java 17) et le rôle.
  - Supprimer le paragraphe « Reportés au rapport de certification ».
  - Dans la colonne « Documents rédigés », retirer les notices (il ne reste que les procédures).
- [ ] **Step 2 : `pipeline.md`.** Décrire les deux chaînes : gateway `/notices/` → `make scraper` → `notices-<date>.json` → `make ingest … COLLECTION=notices_produits` ; ARFF OpenML → Parquet → Spark SQL → `fremtpl2-agregats-<date>.json` (disponible pour l'agrégation #52).
- [ ] **Step 3 : vérifier** : `grep -c "Reportés" docs/donnees/sources.md` → `0`.
- [ ] **Step 4 : commit** — `docs(donnees): cinq sources inventoriées (#45, #51)`
- [ ] **Step 5 : PR 1 en brouillon** vers `main` (issues #45 et #51 citées, sans `Closes`), puis passer la main à Acerola pour la fusion et le déploiement en production. **Arrêt ici jusqu'au déploiement.**

### Task 8 (PR 2, après le déploiement de la PR 1) : instantané de production et bascule de l'ingestion

**Files :**
- Create : `data/raw/notices-<date>.json`
- Modify : `.github/workflows/deploy.yml:521`, `rag/agentinsurflow_rag/cli/ingest.py:4`, `rag/corpus/README.md:10`
- Delete : `rag/corpus/notices_produits/` (4 fichiers)
- Test : `tests/unit/test_deploy.py`

- [ ] **Step 1 : écrire le test qui échoue.** `test_notices_ingerees_depuis_l_instantane_scrape` : `deploy.yml` contient `INSTANTANE="$(ls data/raw/notices-*.json | sort | tail -1)" COLLECTION=notices_produits` et ne contient plus `SOURCE=rag/corpus/notices_produits`.
- [ ] **Step 2 : lancer le test et vérifier l'échec** : `uv run pytest tests/unit/test_deploy.py --no-cov` → FAIL.
- [ ] **Step 3 : scraper la production.** Lancer `make scraper URL=<URL publique de la gateway de prod>`. Vérifier que le manifeste annonce `articles == 4` et que chaque `url_source` est l'URL de prod.
- [ ] **Step 4 : basculer.** Remplacer la ligne 521 de `deploy.yml` par le rejeu de l'instantané. Supprimer les 4 Markdown et mettre à jour la docstring d'`ingest` et `rag/corpus/README.md`.
- [ ] **Step 5 : vérifier** : `make test` → vert ; `grep -rn "corpus/notices_produits" --exclude-dir=docs .` → aucun résultat.
- [ ] **Step 6 : commit et PR 2 en brouillon** — `feat(corpus): notices produits ingérées depuis l'instantané scrapé (#45)`. Après le déploiement par Acerola, contrôle GF6 : `make test-e2e URL=<prod>` (ou la recette de génération de contrat) → le Rédacteur cite la notice du `contrat_type`.
