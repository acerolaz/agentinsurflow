# Paramétrage par agent du cluster — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chaque sous-agent du cluster lit son modèle, sa température, son prompt système, son `max_tokens` et son délai dans un fichier versionné `agentic-cluster/agents.toml`, validé au démarrage et au déploiement, et tracé dans l'audit.

**Architecture:** un value object `ReglageAgent` et ses règles de validation pures dans `domain/` ; un chargeur TOML (`tomllib`) dans `infrastructure/llm/` ; `application/` reçoit les réglages par `Dependances` ; la fabrique LangChain, l'audit et `/health` consomment le réglage ; `deploy.yml` vérifie les modèles sur Foundry.

**Tech Stack:** Python 3.12 (`tomllib`, dataclasses), LangChain v1 / `langchain-openai` 1.7.2, FastAPI, OpenTelemetry, GitHub Actions, Azure CLI.

**Spec:** `docs/superpowers/specs/2026-10-24-parametrage-agents-design.md`

## Global Constraints

- Hexagonal : `domain/` et `application/` n'importent ni `tomllib`, ni Pydantic, ni LangChain, ni OpenTelemetry (`tests/unit/test_architecture_cluster.py`).
- Aucune nouvelle dépendance ; versions inchangées.
- Bornes : `temperature` ∈ [0, 1] ; `max_tokens` entier dans [1, 16 000] ; `delai_s` > 0 ; Σ `delai_s` ≤ `budget_global_s` (`INSURFLOW_BUDGET_S`, défaut 25).
- Agents réglés : exactement `pieces`, `analyste`, `redacteur`, `actuaire` (la Saga n'a pas de LLM).
- Cause d'une réponse tronquée : `budget_tokens` (jamais `llm_ko`).
- Aucune écriture Azure par un agent ; la vérification Foundry est en lecture seule.
- Français partout ; commits avec les trailers `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` et `Claude-Session: https://claude.ai/code/session_01VrE2XvMBbhRrKyrngVjLTJ`.
- Exploration du code par `graphify query` ; `make lint`, `make test`, `make test-integration` verts à la fin de chaque tâche.

## Review Focus

- Un booléen TOML (`max_tokens = true`) passe pour un entier en Python (`bool` ⊂ `int`) : il doit être refusé (test en tâche 1).
- Une température entière (`temperature = 0` ou `1`) est un réglage légitime : acceptée et convertie en `float` (tâche 1).
- Un `prompt` avec un chemin (`"../../secrets.md"`, `"sous/x.md"`) doit être refusé : seul un nom de fichier du dossier des prompts (tâche 1).
- Un fichier TOML mal formé donne une `ReglageInvalide` qui nomme le fichier, pas une trace `tomllib` brute (tâche 2).
- Σ `delai_s` **égale** au budget global est acceptée ; strictement au-dessus, refusée (tâche 1).

---

### Task 1: Domaine — `ReglageAgent` et règles de validation

**Files:**
- Create: `agentic-cluster/agentinsurflow_cluster/domain/reglages.py`
- Test: `agentic-cluster/tests/unit/test_reglages.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ReglageAgent: modele: str; temperature: float; max_tokens: int; delai_s: float; prompt: str`
  - `class ReglageInvalide(ValueError)` — message qui nomme l'agent et la clé.
  - `AGENTS_REGLES: tuple[NomAgent, ...] = ("pieces", "analyste", "redacteur", "actuaire")`
  - `def valider_reglages(brut: Mapping[str, Mapping[str, object]], budget_global_s: float, prompt_existe: Callable[[str], bool]) -> dict[NomAgent, ReglageAgent]`

- [ ] **Step 1: Write the failing tests** (`test_reglages.py`, un dict valide `VALIDE` des quatre agents avec les valeurs du § 3 de la spec, `existe = lambda f: True`)
  - `test_reglages_valides_charges` : 4 entrées, `r["redacteur"] == ReglageAgent("gpt-4.1-mini", 0.2, 1200, 8.0, "redacteur.md")`.
  - `test_agent_manquant_refuse` (sans `actuaire`) et `test_section_inconnue_refusee` (`saga` ajoutée) : `ReglageInvalide`, message contient le nom.
  - `test_cle_inconnue_refusee` (`top_p` dans `pieces`) et `test_cle_manquante_refusee` (sans `modele`).
  - `@pytest.mark.parametrize` température `-0.1`, `1.1`, `"0.5"` refusées ; `0` et `1` acceptées, `isinstance(r["pieces"].temperature, float)`.
  - max_tokens `0`, `16001`, `True`, `1.5` refusés ; `1` et `16000` acceptés.
  - delai_s `0`, `-1` refusés ; `modele = ""` refusé.
  - `test_somme_des_delais_egale_au_budget_acceptee` (budget 13.0 avec 1.5+2+8+1.5) ; `test_somme_des_delais_au_dela_refusee` (budget 12.9).
  - `test_prompt_avec_chemin_refuse` : `"../x.md"`, `"a/b.md"` ; `test_prompt_absent_refuse` : `prompt_existe = lambda f: False`.

- [ ] **Step 2: Run** `uv run pytest agentic-cluster/tests/unit/test_reglages.py --no-cov -q` — Expected: FAIL (module absent).

- [ ] **Step 3: Implement** `domain/reglages.py` (stdlib seulement). `bool` exclu explicitement des nombres ; un `prompt` valide est un nom sans `/` ni `\` ni `..`.

- [ ] **Step 4: Run** la même commande — Expected: PASS ; puis `uv run pytest agentic-cluster/tests/unit/test_architecture_cluster.py --no-cov -q` PASS.

- [ ] **Step 5: Commit** `feat(cluster): réglage par agent, règles de validation pures (domaine)`

### Task 2: Infrastructure — `agents.toml` et son chargeur

**Files:**
- Create: `agentic-cluster/agents.toml` (contenu exact : bloc du § 3 de la spec)
- Create: `agentic-cluster/agentinsurflow_cluster/infrastructure/llm/reglages.py`
- Modify: `agentic-cluster/Dockerfile` (`COPY agentic-cluster/agents.toml agentic-cluster/`, à côté de `garde_fous.env`)
- Test: `agentic-cluster/tests/unit/test_chargeur_reglages.py`

**Interfaces:**
- Consumes: `valider_reglages`, `ReglageInvalide`, `ReglageAgent` (tâche 1) ; `PROMPTS` de `infrastructure/llm/fabrique.py`.
- Produces: `FICHIER_REGLAGES: Path` (= `agentic-cluster/agents.toml`, résolu comme `_FICHIER` de `garde_fous/llm_guard.py`) ; `def charger_reglages(budget_global_s: float, chemin: Path = FICHIER_REGLAGES) -> dict[NomAgent, ReglageAgent]`.

- [ ] **Step 1: Write the failing tests**
  - `test_fichier_du_depot_valide` : `charger_reglages(25.0)` rend les 4 agents, `["pieces"].modele == "gpt-4.1-mini"`.
  - `test_toml_mal_forme` (fichier `tmp_path` contenant `[pieces`) : `ReglageInvalide`, message contient le nom du fichier.
  - `test_prompt_inexistant` : réglage valide sauf `prompt = "absent.md"` ⇒ `ReglageInvalide`.
- [ ] **Step 2: Run** `uv run pytest agentic-cluster/tests/unit/test_chargeur_reglages.py --no-cov -q` — FAIL.
- [ ] **Step 3: Implement** `charger_reglages` : `tomllib.loads`, `TOMLDecodeError` → `ReglageInvalide(f"{chemin.name} : …")`, `prompt_existe = lambda f: (PROMPTS / f).is_file()`.
- [ ] **Step 4: Run** — PASS. `docker build -f agentic-cluster/Dockerfile .` n'est **pas** requis ici (tâche 6).
- [ ] **Step 5: Commit** `feat(cluster): agents.toml versionné et son chargeur`

### Task 3: Branchement — délais, modèle et prompt lus dans le réglage

**Files:**
- Modify: `domain/specs.py` (retirer `delai_s` de `SpecAgent` et des 4 entrées)
- Modify: `application/agents.py` (`Dependances.reglages`, garde de l'agent), `application/evaluation.py:144`
- Modify: `infrastructure/llm/modele.py`, `infrastructure/llm/fabrique.py` (`version_prompt`, prompt système), `infrastructure/entra/config.py` (retirer `azure_openai_deployment`), `api/app.py` (chargement au démarrage), `api/routes.py` (`version_prompt`)
- Modify (tests): `tests/fakes_cluster.py` (`REGLAGES` de test), `tests/unit/test_agents.py`, `test_evaluation.py`, `test_fusion.py:96`, `test_modele.py`, `test_fabrique.py`, `tests/integration/test_api_cluster.py`, `test_jeu_garde_fous.py`

**Interfaces:**
- Consumes: `ReglageAgent` (tâche 1), `charger_reglages` (tâche 2).
- Produces:
  - `Dependances.reglages: Mapping[NomAgent, ReglageAgent]` (champ **obligatoire**, placé après `audit`).
  - `def modele_chat(reglage: ReglageAgent, agent: NomAgent, cfg: ConfigCluster, jetons: JetonsAgents) -> BaseChatModel | None` — `ChatOpenAI(model=reglage.modele, temperature=reglage.temperature, max_tokens=reglage.max_tokens, …)` ; `None` si `not cfg.insurflow_llm_actif` ou `not cfg.llm_audience`.
  - `RedactionLangChain(modele, outils, reglages: Mapping[NomAgent, ReglageAgent])` — prompt système = `PROMPTS / reglages[agent].prompt`.
  - `def version_prompt(fichier: str) -> str` (empreinte de `PROMPTS / fichier`).
  - `composition_reelle` : `reglages = charger_reglages(budget_global_s)` **avant** de charger les scanners ; une `ReglageInvalide` arrête le démarrage (pas de 503 silencieux).

- [ ] **Step 1: Write the failing tests**
  - `test_agents.py::test_garde_de_l_agent_lit_le_delai_du_reglage` : réglage `pieces.delai_s = 0.01`, une rédaction factice qui dort 0.05 s ⇒ rapport `mode == "repli"`.
  - `test_modele.py::test_modele_porte_le_reglage` : `m.model_name == "gpt-4.1-mini"`, `m.temperature == 0.2`, `m.max_tokens == 1200` pour le réglage du Rédacteur ; `test_llm_coupe_rend_none` garde `insurflow_llm_actif=False`.
  - `test_fabrique.py::test_prompt_systeme_du_reglage` : un réglage pointant `analyste.md` pour `pieces` ⇒ le premier message système envoyé au faux modèle est le texte de `analyste.md`.
  - `test_api_cluster.py::test_reglage_invalide_empeche_le_demarrage` : `composition` qui lève `ReglageInvalide` ⇒ le démarrage (`TestClient(app)` en contexte) lève.
- [ ] **Step 2: Run** `uv run pytest agentic-cluster/tests --no-cov -q -m "not lent"` — FAIL sur ces tests.
- [ ] **Step 3: Implement** les signatures ci-dessus ; mettre à jour les 5 constructions de `Dependances` avec `REGLAGES` de `fakes_cluster.py` (valeurs du § 3, construits par `ReglageAgent`, sans lire le fichier).
- [ ] **Step 4: Run** `make lint` et `uv run pytest agentic-cluster/tests --no-cov -q -m "not lent"` — PASS.
- [ ] **Step 5: Commit** `feat(cluster): modèle, température, max_tokens, prompt et délai lus dans le réglage`

### Task 4: Budget de tokens et consommation

**Files:**
- Modify: `infrastructure/llm/fabrique.py`, `application/agents.py`, `domain/models.py` (`Rapport`)
- Test: `tests/unit/test_fabrique.py`, `tests/unit/test_agents.py`

**Interfaces:**
- Produces:
  - `CAUSE_BUDGET = "budget_tokens"` (dans `application/agents.py`, à côté de `CAUSE_PII`, même valeur dans la fabrique).
  - `RedactionPort.rediger` : retour `{"erreur": "budget_tokens"}` si une réponse du modèle est tronquée par `max_tokens` ; sinon le dict habituel **plus** `"usage": {"entree": int, "sortie": int}` (somme des appels de l'agent, d'après `usage_metadata` des messages IA).
  - `Rapport.tokens_entree: int = 0`, `Rapport.tokens_sortie: int = 0` (défauts : compatibles avec les points de reprise existants).

- [ ] **Step 1: Write the failing tests**
  - `test_fabrique.py::test_reponse_tronquee_budget_tokens` : faux modèle dont le message porte `response_metadata={"finish_reason": "length"}` ⇒ `{"erreur": "budget_tokens"}`. Si le builder détecte par `openai.LengthFinishReasonError`, un second cas lève cette exception et attend le même retour.
  - `test_fabrique.py::test_usage_additionne` : deux appels (`usage_metadata` 10/5 puis 20/7) ⇒ `usage == {"entree": 30, "sortie": 12}`.
  - `test_agents.py::test_budget_tokens_repli_cause_distincte` : rédaction factice `{"erreur": "budget_tokens"}` ⇒ `rapport.mode == "repli"`, `rapport.cause == "budget_tokens"`.
  - `test_agents.py::test_tokens_dans_le_rapport` : rédaction factice avec `usage` 30/12 ⇒ `rapport.tokens_entree == 30`.
- [ ] **Step 2: Run** `uv run pytest agentic-cluster/tests/unit/test_fabrique.py agentic-cluster/tests/unit/test_agents.py --no-cov -q` — FAIL.
- [ ] **Step 3: Implement** ; `llm_ko` reste la cause des autres pannes, `garde_fou:pii` inchangé.
- [ ] **Step 4: Run** — PASS ; `make lint` PASS.
- [ ] **Step 5: Commit** `feat(cluster): cause budget_tokens et tokens consommés par agent`

### Task 5: Preuve — audit, span et `/health`

**Files:**
- Modify: `domain/ports.py` (`AuditPort.tracer`), `infrastructure/otel/audit.py`, `application/agents.py` (`executer_agent`), `api/schemas.py` (`SanteReponse`), `api/routes.py` (`sante`), `tests/fakes_cluster.py` (faux audit)
- Test: `tests/unit/test_telemetrie_cluster.py` (ou le test d'audit existant), `tests/integration/test_api_cluster.py`

**Interfaces:**
- Produces:
  - `AuditPort.tracer(..., reglage: ReglageAgent | None = None)` ; `None` pour la Saga.
  - Span `invoke_agent` : `gen_ai.request.model`, `gen_ai.request.temperature`, `gen_ai.request.max_tokens`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` (si `reglage` non `None`).
  - `audit.agent` : clés `modele`, `temperature`, `max_tokens`, `tokens_entree`, `tokens_sortie`.
  - `SanteReponse.reglages: dict[str, ReglageDto]`, `ReglageDto(modele: str, temperature: float, max_tokens: int, delai_s: float, version_prompt: str)` ; `prompts` conservé.

- [ ] **Step 1: Write the failing tests**
  - span d'un agent avec réglage du Rédacteur et tokens 30/12 : les cinq attributs `gen_ai.*` ont ces valeurs ; journal `audit.agent` contient `"modele": "gpt-4.1-mini"`, `"tokens_entree": 30`.
  - span de la Saga (`reglage=None`) : aucun attribut `gen_ai.request.*`.
  - `test_api_cluster.py::test_health_expose_les_reglages` : `GET /health` ⇒ `reglages["actuaire"]["max_tokens"] == 400` et `reglages["actuaire"]["version_prompt"] == prompts["actuaire"]`.
- [ ] **Step 2: Run** les tests ciblés — FAIL.
- [ ] **Step 3: Implement** ; `executer_agent` passe `deps.reglages[nom]`.
- [ ] **Step 4: Run** `make lint` et `uv run pytest agentic-cluster/tests --no-cov -q -m "not lent"` — PASS.
- [ ] **Step 5: Commit** `feat(cluster): réglage et tokens tracés (audit.agent, invoke_agent, /health)`

### Task 6: Déploiement et documentation

**Files:**
- Modify: `.github/workflows/deploy.yml` (étape cluster), `infra/containerapp-cluster.yaml` (retirer `AZURE_OPENAI_DEPLOYMENT`), `docker-compose.yml` (service `agentic-cluster`), `.env.example` (si la variable n'y sert qu'au cluster)
- Delete: `agentic-cluster/llm.env`
- Modify: `agentic-cluster/README.md`, `docs/contrat-personnel.md`

**Interfaces:**
- Consumes: `agentic-cluster/agents.toml` (tâche 2).

- [ ] **Step 1: `deploy.yml`** — remplacer la lecture de `agentic-cluster/llm.env` par une étape **avant** toute mise à jour de Container App : lire `agentic-cluster/agents.toml` **du SHA déployé** (le checkout déjà à `steps.image.outputs.tag`, sinon `git show "$TAG":agentic-cluster/agents.toml`), extraire les modèles (`python3 -c 'import tomllib,sys; …'`), déduire la ressource de `vars.FOUNDRY_ENDPOINT` (`https://<nom>.openai.azure.com`), puis pour chaque modèle `az cognitiveservices account deployment show -n <nom> -g "$RG" --deployment-name <modele> -o none` ; échec ⇒ `::error::modèle <m> absent de Foundry <nom> : déploiement refusé (agentic-cluster/agents.toml)`, `exit 1`. Retirer `AZURE_OPENAI_DEPLOYMENT` de l'`envsubst` du cluster.
- [ ] **Step 2: Vérifier** : `uvx --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"` ; extraire le bloc shell et `bash -n` ; jouer la boucle Foundry à la main depuis le poste (lecture seule) : `gpt-4.1-mini` trouvé, `inexistant` refusé.
- [ ] **Step 3: Docker** : `docker build -f agentic-cluster/Dockerfile -t cluster:reglages .` puis `docker run --rm cluster:reglages python -c "from agentinsurflow_cluster.infrastructure.llm.reglages import charger_reglages; print(sorted(charger_reglages(25.0)))"` ⇒ les 4 agents.
- [ ] **Step 4: Docs** : README du cluster (le fichier, ses bornes, « modifier par PR, vérifié au déploiement ») ; `contrat-personnel.md` : une ligne de preuve (fichier, validation démarrage + déploiement, `audit.agent` / `invoke_agent` / `/health`).
- [ ] **Step 5: Run** `make lint`, `make test`, `make test-integration` — PASS (l'échec connu `rag/…/test_cli_ingest.py::test_rejeu_instantane_n_appelle_pas_piste`, préexistant sur `main`, est toléré).
- [ ] **Step 6: Commit** `feat(deploy): modèles du cluster vérifiés sur Foundry ; llm.env remplacé par agents.toml`

### Task 7: Dossier de conception du brief4 (PDF)

**Files:**
- Create: `brief4/avenants-2026-10-24.html` (source), `brief4/dossier-conception-v1.1.pdf` (sortie)
- Inchangé : `brief4/dossier-conception-v1.pdf` (l'original reste, c'est lui qui « fait foi » jusqu'à validation)

**Décision (mon choix, faute de source Markdown à jour du PDF du brief4, généré par pypdf)** : on **ajoute** au PDF existant une section « Avenants du 24/10/2026 », sans régénérer le dossier.

- [ ] **Step 1: Rédiger** `avenants-2026-10-24.html` (français, une page par avenant si besoin) : A6 la Saga (automate déterministe, sans rôle LLM ; noms techniques conservés) ; observations écrites tant que le dossier n'est pas décidé (statut `actif` accepté) ; modèle propre au cluster (Kimi-K2.5 ≈ 14 s incompatible avec les délais par agent, `gpt-4.1-mini`) ; paramétrage par agent (`agents.toml` : modèle, température, prompt système, `max_tokens`, délai ; validation ; cause `budget_tokens` ; preuve). Chaque avenant : décision, raison, impact sur les critères K (K5, K9).
- [ ] **Step 2: Rendre** en PDF : `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=brief4/avenants-2026-10-24.pdf brief4/avenants-2026-10-24.html`.
- [ ] **Step 3: Fusionner** : `uv run --with pypdf python -c "from pypdf import PdfWriter; w=PdfWriter(); [w.append(f) for f in ('brief4/dossier-conception-v1.pdf','brief4/avenants-2026-10-24.pdf')]; w.write('brief4/dossier-conception-v1.1.pdf')"`.
- [ ] **Step 4: Vérifier** : nombre de pages = 55 + pages des avenants ; ouvrir la dernière page (lecture par l'outil `Read` sur le PDF, pages de fin).
- [ ] **Step 5:** pas de commit (`brief4/` est hors du dépôt `brief2/src`) ; signaler à Acerola les deux fichiers produits.
