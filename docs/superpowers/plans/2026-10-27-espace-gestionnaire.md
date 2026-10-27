# Espace gestionnaire — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** livrer pour le 30/10 l'espace gestionnaire (SPA servie par la gateway) qui lance le cluster sur un dossier, en montre la progression, permet pause/reprise, relance tracée, validation et contrat, plus un tchat sur le corpus.

**Architecture :** la page est faite de fichiers statiques sous `/app/` de la gateway (HTML + JS en modules ES, sans build), avec MSAL.js versionné dans le dépôt. Elle n'appelle que des routes de la gateway. Le back gagne :
- côté underwriting-admin : lecture de l'état, relances, contrat généré ;
- côté cluster : pause/reprise et un 429 lisible ;
- côté seed : un gestionnaire C pour la CI.

Chaque service garde son architecture (Python hexagonal, C# Clean Architecture).

**Tech Stack :** FastAPI + LangGraph (cluster), ASP.NET 10 minimal API + EF Core (underwriting-admin), YARP (gateway), JavaScript ES2022 sans dépendance hors `msal-browser`, `node --test` pour la logique pure de la page.

**Spec :** `docs/superpowers/specs/2026-10-27-espace-gestionnaire-design.md` (approuvée le 27/10). Issues : #38 (parapluie), #103, #104, #101, #100, #122, #129 (pause), #130 (relance).

## Global Constraints

- Seule la gateway est exposée ; chaque service **revalide** le jeton ; erreurs en ProblemDetails avec un `code`.
- BOLA : `gestionnaire_id` = claim `oid`, jamais un paramètre. Un contrat d'un autre gestionnaire renvoie le **même 404 `CONTRAT_INTROUVABLE`** qu'un contrat inexistant.
- underwriting-admin : lecture **uniquement par `vue_contrat_minimisee`** ; jamais de nom, d'adresse ni de numéro de permis dans une réponse ou un span ; JSON en **snake_case** ; SQL paramétré ; migrations EF Core seulement.
- Python : `domain/` et `application/` n'importent ni FastAPI, ni Pydantic, ni SDK (`test_architecture.py`).
- Aucun secret dans le dépôt ; écritures Azure/Entra rédigées dans `infra/*.sh`, **lancées à la main par Acerola** ; variables GitHub idem (commandes `gh variable set` données, pas lancées).
- Versions (`pyproject.toml`) inchangées sans accord d'Acerola.
- Français partout (code métier, tests, docs, textes de la page).
- Page : **aucun `innerHTML` avec une donnée venue de l'API** (`textContent` ou nœuds créés) ; pas de CDN ; CSP `script-src 'self'`.
- Relance : **aucun e-mail réel** avant le 15/11 (#123) ; la trace ne porte jamais le texte du mail.
- Chaque test annonce son niveau (TU / TI / E2E) selon `.claude/rules/testing-pyramid.md`.
- Une branche : `feat/GenererContrat` ; PR en brouillon ; jamais de push sur `main`.

## Review Focus

1. **Double clic sur « Lancer »** (deux `POST …/evaluation` simultanés). Attendu : le second reçoit `409 EVALUATION_EN_COURS`, sans seconde tentative. Testé en tâche 6.
2. **Pause demandée trop tard** (évaluation déjà en validation ou terminée). Attendu : la demande est oubliée et ne met pas en pause l'évaluation suivante. Testé en tâche 6.
3. **Reprise après une pause : observations perdues.** Elles ne vivent que dans `Contexte.memoire`, le temps d'une exécution. Attendu : le Rédacteur les revoit à la reprise et le budget de temps repart de zéro. Testé en tâche 6.
4. **Lien direct vers le dossier d'un autre gestionnaire** (`#/dossiers/AIF-2026-000004` ouvert par A). Attendu : `404` sur `…/etat`, `…/relances` et `…/contrat`, et la page affiche « Contrat introuvable » sans rien d'autre. Testé en tâches 2, 3 et 4.
5. **Texte de relance hostile** (vide, plus de 4 000 caractères, balises HTML). Attendu : `400 TEXTE_INVALIDE` pour vide ou trop long. Le HTML est stocké tel quel puis affiché comme du texte. Testé en tâches 3 (API) et 10 (règle `textContent`).

---

### Task 1 : seed — gestionnaire C pour la CI et dossier « refus » pour A

**Files :**
- Modify : `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Infrastructure/Dossiers/SeedDossiers.cs`
- Create : `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Infrastructure/Dossiers/Migrations/<horodatage>_SeedGestionnaireC.cs` (+ Designer, par `dotnet ef migrations add SeedGestionnaireC`)
- Modify : `.github/workflows/deploy.yml` (env `SEED_GESTIONNAIRE_C` à côté de `SEED_GESTIONNAIRE_A`, l. 74), `.env.example`
- Test : `underwriting-admin/tests/…Infrastructure.Tests/SeedDossiersTests.cs` (créer si absent, dans le projet de test Infrastructure existant)

**Interfaces :**
- Produces : `SeedDossiers.SqlC(string? gestionnaireC) -> string` et `SeedDossiers.SqlPiecesC(string? gestionnaireC) -> string`. Dossiers **7, 8, 9** (`AIF-2026-000007` à `000009`), mêmes profils que 1, 5 et 6, avec relevé et permis. Sans variable : `"SELECT 1"`.
- Produces : si aucun dossier de A n'est classé `refus` par le barème, `SqlRefusA(string? gestionnaireA)` ajoute le **dossier 10** (`AIF-2026-000010`) pour A, avec un profil que le barème refuse. La même migration l'applique.
- `Sql(a, b)` et `SqlPieces(a, b)` gardent leur signature (migrations déjà appliquées).

- [ ] **Step 1 : établir la classe de risque des dossiers 1 et 2.** Utiliser le barème de `fonction-calcul` (TU existants de `fonction-calcul/tests/unit`) sur leurs profils. Noter le résultat dans le message de commit. Si l'un est `refus`, ne pas créer de dossier 10 et noter son numéro pour la tâche 12.
- [ ] **Step 2 : test (TU) qui échoue.**
  ```csharp
  [Fact] public void SqlC_sans_variable_ne_seme_rien() => Assert.Equal("SELECT 1", SeedDossiers.SqlC(null));
  [Fact] public void SqlC_seme_trois_dossiers_a_partir_de_7()
  { var sql = SeedDossiers.SqlC("11111111-1111-1111-1111-111111111111");
    Assert.Contains("AIF-2026-000007", sql); Assert.Contains("AIF-2026-000009", sql); Assert.DoesNotContain("AIF-2026-000010", sql); }
  [Fact] public void SqlC_refuse_un_oid_qui_n_est_pas_un_guid() => Assert.Throws<InvalidOperationException>(() => SeedDossiers.SqlC("x'; DROP"));
  ```
  Si un dossier 10 est créé, ajouter un test de `fonction-calcul` : `test_profil_dossier_10_classe_refus` (le barème rend `classe == "refus"`).
- [ ] **Step 3 : lancer `dotnet test underwriting-admin --filter SeedDossiersTests`.** Attendu : FAIL (`SqlC` inexistant).
- [ ] **Step 4 : implémenter `SqlC`, `SqlPiecesC` (et `SqlRefusA` si besoin) puis la migration `SeedGestionnaireC`.** Elle lit `SEED_GESTIONNAIRE_C` (et `SEED_GESTIONNAIRE_A` pour le dossier 10) ; son `Down` est vide, comme `Seed`. Le champ `bool GestionnaireA` devient `char Gestionnaire` (`'A'`, `'B'`, `'C'`).
- [ ] **Step 5 : `dotnet test underwriting-admin`.** Attendu : PASS (tests existants compris).
- [ ] **Step 6 : commit** `feat(underwriting): gestionnaire C de la CI dans le seed (#100)`.

### Task 2 : underwriting-admin — `GET /api/contrats/{n}/etat`

**Files :**
- Create : `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Domain/EtatLu.cs`, `…Application/LireEtat.cs`
- Modify : `…Application/IDepotDossiers.cs`, `…Infrastructure/Dossiers/DepotDossiersEf.cs`, `…Api/ContratsEndpoints.cs`, enregistrement DI (`DossiersServices.cs` ou `Program.cs`, là où `ConsulterContrat` l'est)
- Test : `underwriting-admin/tests/AgentInsurFlow.UnderwritingAdmin.Api.Tests/EtatTests.cs` (TI), `…Domain.Tests/ReglesEtatTests.cs` (TU)

**Interfaces :**
- Produces (Domain) :
  ```csharp
  public sealed record RapportLu(string Agent, string Mode, string? Cause, string TraceId, DateTimeOffset CreeLe);
  public sealed record EtatLu(string? StatutParcours, int Tentative, int NbRelances,
      IReadOnlyList<RapportLu> Rapports, IReadOnlyDictionary<string, string> Sections); // valeur = JSON brut
  ```
  `ReglesEtat.SectionsLisibles = { "pieces", "risque", "sources", "fiche", "prime", "validation" }` : jamais `dossier` ni `pilotage`.
- Produces (port) : `Task<EtatLu?> IDepotDossiers.LireEtat(string gestionnaireId, string numeroContrat, CancellationToken ct)`. Il rend `null` si le contrat est inexistant ou à un autre gestionnaire. Un contrat sans état rend `EtatLu(null, 0, 0, [], {})`. Les rapports et sections sont ceux de la **tentative courante**, rapports triés par `cree_le`.
- Produces (HTTP) : `GET /api/contrats/{numero_contrat}/etat` → 200. Exemple de corps :
  ```json
  {"statut_parcours":"EN_COURS","tentative":2,"nb_relances":0,
   "rapports":[{"agent":"pieces","mode":"llm","cause":null,"trace_id":"…","cree_le":"…"}],
   "sections":{"pieces":{…}}}
  ```
  Réponses d'erreur : `403 ACCES_REFUSE`, `404 CONTRAT_INTROUVABLE`. `.WithName("LireEtat")` dans l'OpenAPI.

- [ ] **Step 1 : TU** `SectionsLisibles_exclut_dossier_et_pilotage` : `Assert.DoesNotContain("dossier", ReglesEtat.SectionsLisibles)` et `Assert.DoesNotContain("pilotage", …)`.
- [ ] **Step 2 : TI** dans `EtatTests` (reprendre le banc `Usine` existant) :
  - `Lire_etat_apres_put_rend_rapports_et_sections_lisibles` : un `PUT …/etat` (jeton du MCP, comme les tests existants) avec les sections `dossier`, `pieces`, `pilotage`, puis un `GET` qui rend 200. Les `sections` ne contiennent que `pieces` ; le rapport a `agent`, `mode`, `trace_id` et `cree_le` non vide.
  - `Lire_etat_sans_evaluation_200_vide` : `statut_parcours` null, `rapports` vide.
  - `Lire_etat_autre_gestionnaire_404` : `code == "CONTRAT_INTROUVABLE"`.
- [ ] **Step 3 : `dotnet test underwriting-admin --filter "EtatTests|ReglesEtatTests"`.** Attendu : FAIL.
- [ ] **Step 4 : implémenter** `LireEtat` (cas d'usage = appel du port), `DepotDossiersEf.LireEtat` (borné par `IdContrat`-équivalent sur `gestionnaire_id`, filtre `SectionsLisibles`) et l'endpoint. Les sections sont rendues en `JsonElement` par le DTO de l'API.
- [ ] **Step 5 : relancer le filtre.** Attendu : PASS. Puis `dotnet test underwriting-admin` : PASS.
- [ ] **Step 6 : commit** `feat(underwriting): lecture de l'état du dossier (#104)`.

### Task 3 : underwriting-admin — relances enregistrées et tracées (#130)

**Files :**
- Create : `…Domain/ReglesRelance.cs`, `…Application/EnregistrerRelance.cs`, migration `<horodatage>_Relances.cs` (table `relance`)
- Modify : `…Application/IDepotEcritures.cs`, `…Infrastructure/Dossiers/DepotEcrituresEf.cs`, `Entites.cs`, `DossiersDbContext.cs`, `…Api/EcrituresEndpoints.cs`
- Test : `…Domain.Tests/ReglesRelanceTests.cs` (TU), `…Api.Tests/RelancesTests.cs` (TI)

**Interfaces :**
- Produces (Domain) : `ReglesRelance.Max = 3`, `ReglesRelance.TexteMax = 4000`. `string? ReglesRelance.Refus(int dejaEnvoyees, string texte, IReadOnlyList<string> pieces)` rend :
  - `"RELANCES_EPUISEES"` si `dejaEnvoyees >= 3` ;
  - `"TEXTE_INVALIDE"` si le texte est vide ou blanc, ou dépasse 4 000 caractères ;
  - `"PIECES_INVALIDES"` si `pieces` est vide ou si un élément ne respecte pas `^[a-z_]{1,40}$` ;
  - sinon `null`.
- Produces (port) : `Task<ResultatRelance> IDepotEcritures.EnregistrerRelance(string gestionnaireId, string numeroContrat, string texte, IReadOnlyList<string> pieces, CancellationToken ct)` avec `public sealed record ResultatRelance(int? Rang, string? CodeRefus)`. `Rang=null, CodeRefus=null` = 404.
- Table `relance` (`numero_contrat`, `rang`, `texte`, `pieces` jsonb, `envoyee_le`, `envoyee_par`), PK `(numero_contrat, rang)`. Dans la même transaction, `etat_dossier.nb_relances` = nombre de lignes, si l'état existe.
- Produces (HTTP) : `POST /api/contrats/{numero_contrat}/relances`, corps `{"texte": "…", "pieces": ["releve_information"]}`.
  - Succès : `201 {"rang": 1, "max": 3}`.
  - Erreurs : `400 TEXTE_INVALIDE` ou `PIECES_INVALIDES`, `409 RELANCES_EPUISEES`, `404 CONTRAT_INTROUVABLE`.
  - Span courant : tags `relance.rang`, `relance.max`, `relance.pieces` (types joints par `,`), **jamais** le texte.
  - Aucune route gateway à ajouter : `underwriting-contrats` (`/api/contrats/{**reste}`) la couvre. Choix assumé à la place du `/v1/souscriptions/{n}/relances` de la spec : même service, même politique, une route de moins.

- [ ] **Step 1 : TU** `ReglesRelanceTests` (une `[Theory]`) :
  - `(0, "Bonjour", ["permis"])` donne `null` ;
  - `(3, "Bonjour", ["permis"])` donne `"RELANCES_EPUISEES"` ;
  - `(0, "  ", ["permis"])` et `(0, new string('a', 4001), ["permis"])` donnent `"TEXTE_INVALIDE"` ;
  - `(0, "Bonjour", [])` et `(0, "Bonjour", ["Permis!"])` donnent `"PIECES_INVALIDES"`.
- [ ] **Step 2 : TI** `RelancesTests` :
  - `Trois_relances_puis_409` : rangs 1, 2, 3, puis `409 RELANCES_EPUISEES`.
  - `Relance_autre_gestionnaire_404`.
  - `Texte_vide_400` : code `TEXTE_INVALIDE`.
  - `Texte_html_stocke_tel_quel` : `<b>x</b>` enregistré à l'identique.
  - `Relance_met_a_jour_nb_relances` : après un `PUT …/etat` puis une relance, `GET …/etat` rend `nb_relances == 1`.
  - `Span_porte_le_rang_pas_le_texte` : avec l'exportateur en mémoire des tests de traces existants, le tag `relance.rang` vaut `1` et aucun tag ne contient le texte.
- [ ] **Step 3 : `dotnet test underwriting-admin --filter "Relance"`.** Attendu : FAIL.
- [ ] **Step 4 : implémenter** la règle, le cas d'usage (`StatutContrat` puis `null` → 404 ; refus de la règle ; écriture), le dépôt (rang = `COUNT + 1` dans la transaction ; `envoyee_par` = oid) et l'endpoint.
- [ ] **Step 5 : `dotnet test underwriting-admin`.** Attendu : PASS.
- [ ] **Step 6 : commit** `feat(underwriting): relance modifiable enregistrée et tracée, sans envoi (#130)`.

### Task 4 : contrat généré — `GET /api/contrats/{n}/contrat` et route publique (#101)

**Files :**
- Create : `…Domain/ContratGenere.cs`, `…Application/LireContratGenere.cs`
- Modify : `IDepotDossiers.cs`, `DepotDossiersEf.cs`, `ContratsEndpoints.cs`, `gateway/src/AgentInsurFlow.Gateway.Api/appsettings.Routes.json`
- Test : `…Api.Tests/ContratGenereTests.cs` (TI), `gateway/tests/…/RoutageTests.cs` (TI)

**Interfaces :**
- Produces (Domain) :
  ```csharp
  public sealed record ContratGenere(string NumeroContrat, string Formule, string ContratType, DateOnly DateEffet,
      string PrimeTtcAnnuelle, string PrimeMensuelle, string VersionBareme, string VersionFormule,
      IReadOnlyList<string> Motifs, IReadOnlyList<string> Citations, string ValidePar, DateTimeOffset ValideLe);
  ```
  Champs repris de la fiche et de la prime en brouillon et des sections `fiche`, `prime` et `validation` de l'état. `ValidePar` = oid de l'auteur de la validation, **pas** un nom.
- Produces (port) : `Task<(ContratGenere? Contrat, bool Existe)> IDepotDossiers.LireContratGenere(string gestionnaireId, string numeroContrat, CancellationToken ct)`. `Existe=false` donne 404 ; `Existe=true` avec un contrat `null` donne `409 CONTRAT_NON_ACCEPTE` (statut différent d'`ACCEPTE`).
- Produces (HTTP) :
  - Service : `GET /api/contrats/{n}/contrat` → 200 (snake_case), `404`, `409 CONTRAT_NON_ACCEPTE`.
  - Gateway : route `underwriting-contrat-genere`, `GET /v1/souscriptions/{numero_contrat}/contrat` → `PathPattern /api/contrats/{numero_contrat}/contrat`, politique `underwriting-gestionnaire`.

- [ ] **Step 1 : TI** `ContratGenereTests` :
  - `Contrat_accepte_200_sans_donnee_identifiante` : la réponse ne contient ni `Nom`, ni `rue`, ni `PERMIS`.
  - `Contrat_en_analyse_409` : code `CONTRAT_NON_ACCEPTE`.
  - `Contrat_autre_gestionnaire_404`.
  - Gateway, dans `RoutageTests` : `GET /v1/souscriptions/AIF-2026-0001/contrat` arrive à underwriting sur `/api/contrats/AIF-2026-0001/contrat` avec le jeton.
- [ ] **Step 2 : lancer les filtres** (`dotnet test underwriting-admin --filter ContratGenere`, `make gateway-test`). Attendu : FAIL.
- [ ] **Step 3 : implémenter** le record, le cas d'usage, le dépôt, l'endpoint et la route YARP.
- [ ] **Step 4 : relancer.** Attendu : PASS.
- [ ] **Step 5 : commit** `feat(contrat): vue du contrat généré après ACCEPTE (#101)`.

### Task 5 : cluster — un 429 de la gateway reste un 429 (#122)

**Files :**
- Modify : `agentic-cluster/agentinsurflow_cluster/infrastructure/mcp/client.py`, `agentic-cluster/agentinsurflow_cluster/api/routes.py`
- Test : `agentic-cluster/tests/unit/test_client_mcp.py` (TU, `httpx.MockTransport` ; créer ou compléter le fichier existant du client), `agentic-cluster/tests/integration/test_api_cluster.py` (TI)

**Interfaces :**
- Produces : `ErreurOutil("TROP_DE_REQUETES", <retry_after en secondes, str>)`. Elle est levée par `ClientMcpGateway.appeler` quand une `httpx.HTTPStatusError` de statut 429 survient, seule ou feuille d'un `BaseExceptionGroup`. `retry_after` vient de l'en-tête `Retry-After`, `"60"` à défaut.
- Produces : `_outil_en_echec` traduit `TROP_DE_REQUETES` en `Probleme(429, "TROP_DE_REQUETES", "Trop de requêtes, réessayez dans quelques secondes", {"Retry-After": e.args[0]})`.

- [ ] **Step 1 : TU** `test_429_de_la_gateway_devient_trop_de_requetes` : un `MockTransport` qui rend `429` avec `Retry-After: 17`. `pytest.raises(ErreurOutil)` et `e.code == "TROP_DE_REQUETES"`, `str(e) == "17"`. Et `test_500_reste_mcp_indisponible`.
- [ ] **Step 2 : TI** `test_outil_en_429_rend_429_avec_retry_after` : `FakeOutils` lève `ErreurOutil("TROP_DE_REQUETES", "17")` sur `get_contrat`. La réponse est `429`, `json()["code"] == "TROP_DE_REQUETES"` et `headers["retry-after"] == "17"`.
- [ ] **Step 3 : TI** `test_une_evaluation_complete_tient_deux_fois_dans_les_limites` : une évaluation `acceptable` complète avec les faux ports, puis on compte les appels de `FakeOutils` par émetteur (`agent` ou `saga`). Chaque compte est `<= 30` (limite `Mcp` = 60/min, partition `oid|azp`, divisée par deux évaluations). Le nombre d'appels à `FakeRedaction` est `<= 15` (limite `Llm` = 30/min, partition `azp` seule).
- [ ] **Step 4 : `uv run pytest agentic-cluster/tests -k "429 or limites or mcp_indisponible" --no-cov`.** Attendu : FAIL sur les deux premiers tests, PASS sur le comptage (sinon : relever les limites dans `gateway/.../appsettings.json` à `2 × max mesuré` et l'écrire dans le commit).
- [ ] **Step 5 : implémenter** la détection du 429 dans `client.py` (avant le `except httpx.HTTPError` générique) et la traduction dans `routes.py`.
- [ ] **Step 6 : relancer.** Attendu : PASS. Puis `make test` : PASS.
- [ ] **Step 7 : commit** `fix(cluster): une 429 de la gateway reste une 429 lisible (#122)`.

### Task 6 : cluster — pause entre les étapes, reprise, évaluation déjà en cours (#129)

**Files :**
- Modify : `agentic-cluster/agentinsurflow_cluster/application/evaluation.py`, `…/infrastructure/langgraph/graphe.py`, `…/api/routes.py`, `…/api/schemas.py`
- Modify : `gateway/src/AgentInsurFlow.Gateway.Api/appsettings.Routes.json` (route `cluster-pause`)
- Test : `agentic-cluster/tests/integration/test_api_cluster.py` (TI), `agentic-cluster/tests/unit/test_evaluation.py` (TU), `gateway/tests/…/ClusterTests.cs` (TI)

**Interfaces :**
- Produces (application) : `async def relire_observations(numero: str, jeton: str, deps: Dependances) -> str | None`. Elle appelle `get_contrat` pour la Saga et rend `observations`, ou `None`. Aucune garde ni audit : `entree_bloquee` est déjà dans l'état.
- Produces (application) : `class EvaluationEnCours(Exception)`.
- Produces (infrastructure) :
  - `ServiceEvaluation.demander_pause(numero: str, oid: str) -> None`. Elle fait le contrôle BOLA via `_controler_proprietaire` mais ne prend **pas** le verrou, et ajoute `numero` à `self._pauses: set[str]`.
  - `ServiceEvaluation.evaluer` lève `EvaluationEnCours` si `self._verrou(numero).locked()`.
- Produces (graphe) :
  - `apres_pas` rend `"pause"` si le numéro est dans `_pauses` et que le dossier n'est pas `termine` ; le numéro est alors retiré de `_pauses`.
  - Nœud `pause` : écrit l'état avec `statut_parcours="EN_PAUSE"` (via `evaluation._enregistrer_etat`, rendue publique sous le nom `enregistrer_etat`). Il pose ensuite `interrupt({"numero_contrat": numero, "pause": True})`. À la reprise, il remet `memoire["observations"] = await relire_observations(...)` et renvoie `{"debut": deps.horloge(), "statut": None}`, puis l'arête mène à `pas`.
  - `proposer` retire le numéro de `_pauses` (une demande tardive est oubliée).
- Produces (service) :
  - `Resultat.statut == "EN_PAUSE"` quand l'instantané attend sur le nœud `pause`.
  - `evaluer` sur un dossier en pause reprend par `Command(resume=True)`, sans incrémenter `tentative`.
  - `reviser` sur un dossier en pause lève `AucuneRevueEnAttente`.
  - `_en_pause` ne vaut que pour le nœud `valider` (renommer en `_attend_revue`).
- Produces (HTTP) :
  - `POST /evaluations/{numero_contrat}/pause` → `202 {"pause": "demandee"}`, `404 CONTRAT_INTROUVABLE`.
  - `EvaluationReponse.statut: Literal["EN_ANALYSE", "REVUE_HUMAINE", "EN_PAUSE"]`.
  - `409 EVALUATION_EN_COURS` (« Une évaluation est déjà en cours pour ce dossier »).
  - Gateway : `POST /v1/souscriptions/{numero_contrat}/pause` → `/evaluations/{numero_contrat}/pause`, `cluster-gestionnaire`, `RateLimiterPolicy: cluster`.

- [ ] **Step 1 : TU** `test_relire_observations_lit_le_contrat_sans_audit` : `FakeOutils` reçoit `get_contrat` et `FakeAudit` n'a aucun enregistrement.
- [ ] **Step 2 : TI** dans `test_api_cluster.py` :
  - `test_pause_avant_evaluation_arrete_apres_le_premier_agent` : `POST …/pause` → 202 ; `POST /evaluations/{n}` → 200 `statut == "EN_PAUSE"` ; `len(synthese) == 1` ; dernier `enregistrer_etat` reçu avec `statut_parcours == "EN_PAUSE"`.
  - `test_reprise_va_au_bout_sans_nouvelle_tentative_et_revoit_les_observations` : après la pause, `POST /evaluations/{n}` → `EN_ANALYSE`. La `tentative` de l'état reste à 1, et la vue du Rédacteur (`FakeRedaction`) contient les observations du `CONTRAT` de test.
  - `test_reprise_apres_longue_pause_ne_depasse_pas_le_budget` : avancer l'horloge des dépendances de 3 600 s pendant la pause. La reprise rend `EN_ANALYSE`, pas une revue humaine `duree`.
  - `test_revue_pendant_la_pause_409` : `code == "AUCUNE_REVUE_EN_ATTENTE"`.
  - `test_pause_apres_proposition_oubliee` : une évaluation complète (`EN_ANALYSE`), puis une pause, puis une revue `REFUSE`. Une nouvelle évaluation du même dossier répond `409 DOSSIER_DECIDE`, et `_pauses` est vide.
  - `test_pause_autre_gestionnaire_404`.
  - `test_deux_evaluations_simultanees_la_seconde_409_en_cours` : `asyncio.gather` de deux `POST`, avec un `FakeRedaction` ralenti (`asyncio.sleep(0.2)`). On obtient un 200 et un `409 EVALUATION_EN_COURS`.
- [ ] **Step 3 : TI gateway** `ClusterTests` : ajouter `("/v1/souscriptions/AIF-2026-0001/pause", "/evaluations/AIF-2026-0001/pause", null)` à la `[Theory]` de relais.
- [ ] **Step 4 : lancer** `uv run pytest agentic-cluster/tests -k "pause or reprise or simultanees or relire" --no-cov` et `make gateway-test`. Attendu : FAIL.
- [ ] **Step 5 : implémenter**, dans l'ordre : application, graphe, service, routes et schémas, route YARP.
- [ ] **Step 6 : relancer** puis `make test-integration` et `make gateway-test`. Attendu : PASS, tests existants compris (`test_evaluation_en_analyse_puis_rejeu_409_puis_revue_accepte` toujours vert).
- [ ] **Step 7 : commit** `feat(cluster): pause entre les étapes et reprise au point de reprise (#129)`.

### Task 7 : gateway — page statique `/app/`, sa configuration et sa CSP

**Files :**
- Modify : `gateway/src/AgentInsurFlow.Gateway.Api/Program.cs`, `appsettings.json`, `AgentInsurFlow.Gateway.Api.csproj` (copier `wwwroot`)
- Create : `gateway/src/AgentInsurFlow.Gateway.Api/wwwroot/app/index.html` (coquille minimale, remplie en tâche 8)
- Create : `gateway/src/AgentInsurFlow.Gateway.Api/wwwroot/app/vendor/msal-browser.min.js` et `vendor/README.md`
- Test : `gateway/tests/AgentInsurFlow.Gateway.Api.Tests/EspaceTests.cs` (TI), `RoutageTests.cs`

**Interfaces :**
- Produces (HTTP, anonyme, sans limite de débit) :
  - `GET /app/` sert `index.html`, et `GET /app/*` les fichiers statiques. En-tête `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://login.microsoftonline.com; frame-src https://login.microsoftonline.com; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`.
  - `GET /app/config.json` → `{"client_id","authority","scopes":{"rag","underwriting","cluster"},"comptes":{"A","B"}}`, lu dans la section `Espace` :
    - `Espace:ClientId`, `SWAGGER_CLIENT_ID` à défaut ;
    - `Espace:Authority` ;
    - `Espace:Scopes:Rag`, `Espace:Scopes:Underwriting`, `Espace:Scopes:Cluster` ;
    - `Espace:Comptes:A`, `Espace:Comptes:B` : UPN servant de `loginHint`, pas des secrets.
- `msal-browser` : dernière version qui publie le bundle UMD `lib/msal-browser.min.js`, copiée telle quelle. La version et l'empreinte SHA-384 sont notées dans `vendor/README.md`, et l'attribut `integrity` dans `index.html`. Pas de npm dans le dépôt.

- [ ] **Step 1 : TI** `EspaceTests` :
  - `Page_servie_sans_jeton_avec_csp` : 200, `text/html`, la CSP contient `script-src 'self'`.
  - `Config_sans_secret` : 200, JSON avec `client_id` et `scopes.cluster` ; aucune clé ne contient `secret`.
  - `Swagger_toujours_a_la_racine` : `GET /` reste 200.
  - `Etat_get_relaye_a_underwriting_avec_la_politique_gestionnaire` : `GET /api/contrats/AIF-2026-0001/etat` avec un jeton underwriting `Gestionnaire` arrive à underwriting. Un `PUT` sur le même chemin sans rôle MCP reste refusé, comme aujourd'hui.
- [ ] **Step 2 : `make gateway-test`.** Attendu : FAIL.
- [ ] **Step 3 : implémenter.**
  - Dans le pipeline, avant `UseAuthentication`, `UseStaticFiles` sur `RequestPath "/app"`, avec `OnPrepareResponse` qui pose la CSP.
  - Ajouter `UseDefaultFiles` pour `/app/`.
  - `MapGet("/app/config.json")` avec `.AllowAnonymous().DisableRateLimiting()`.
  - Télécharger `msal-browser` depuis le registre npm (`npm pack @azure/msal-browser@<version>` dans `$CLAUDE_JOB_DIR/tmp`, puis extraire `lib/msal-browser.min.js`).
- [ ] **Step 4 : `make gateway-test`.** Attendu : PASS.
- [ ] **Step 5 : commit** `feat(gateway): espace gestionnaire servi sous /app avec CSP stricte (#103)`.

### Task 8 : page — connexion A/B, onglets, thème, portefeuille, tchat (#103)

**Files :**
- Create : `gateway/src/AgentInsurFlow.Gateway.Api/wwwroot/app/{index.html, app.css, app.js, auth.js, api.js, logique.js}`
- Create : `gateway/tests/espace/logique.test.mjs`
- Modify : `Makefile` (cible `espace-test: ## logique pure de la page (node --test)`, ajoutée à `test`), `.github/workflows/ci-cd.yml` (étape `make espace-test` dans le job des tests)

**Interfaces :**
- Produces (`logique.js`, fonctions pures, modules ES, sans DOM) :
  - `routeDepuisHash(hash: string) -> {vue: "connexion"|"dossiers"|"dossier"|"tchat", numero?: string}`. Elle accepte `#/dossiers`, `#/dossiers/AIF-2026-000004` et `#/tchat`. Un numéro hors `^AIF-\d{4}-\d{6}$` donne `{vue: "dossiers"}`.
  - `themeInitial(stocke: string|null, prefereSombre: boolean) -> "clair"|"sombre"`.
  - `messageProbleme(statut: number, code?: string) -> string` :
    - 404 → « Contrat introuvable » ;
    - 409 `EVALUATION_EN_COURS` → « Une évaluation est déjà en cours pour ce dossier » ;
    - 429 → « Trop de requêtes, réessayez dans quelques secondes » ;
    - 502 ou 503 → « Service temporairement indisponible » ;
    - autre cas → « Une erreur est survenue ».
- Produces (`api.js`) : `appeler(methode, chemin, {portee, corps}) -> Promise<{statut, json, entetes}>`. Elle prend un jeton par `auth.jeton(portee)` (`acquireTokenSilent`, puis `acquireTokenRedirect` si l'interaction est requise), puis réessaie **une fois** sur 401 avec un jeton forcé (`forceRefresh: true`).
- Produces (`auth.js`) : `connecter(compte: "A"|"B")` (`loginRedirect` avec `loginHint = config.comptes[compte]`), `deconnecter()`, `jeton(portee: "rag"|"underwriting"|"cluster") -> Promise<string>`, `compteCourant() -> {nom, oid} | null`.
- Écrans (maquette v2 de la spec) :
  - Connexion : deux cartes A et B, en `<input type=radio>` avec labels.
  - En-tête : `role="tablist"`, flèches gauche/droite entre onglets, bouton thème avec `aria-pressed`, déconnexion.
  - Portefeuille : `GET /api/contrats` (portée `underwriting`), tableau où chaque ligne contient un lien `<a href="#/dossiers/…">`.
  - Tchat : `POST /api/reponses` `{texte}` (portée `rag`), fil de messages, sources sous chaque réponse (`titre`/`article`, lien quand l'extrait en porte un), `aria-live="polite"` sur le fil.
  - Thème : attribut `data-theme` sur `<html>`, valeur gardée dans `localStorage` (try/catch).

- [ ] **Step 1 : tests** `logique.test.mjs` (`node:test`, `node:assert/strict`) :
  - `routeDepuisHash("#/dossiers/AIF-2026-000004")` donne `{vue: "dossier", numero: "AIF-2026-000004"}` ;
  - `routeDepuisHash("#/dossiers/<script>")` donne `{vue: "dossiers"}` ;
  - `themeInitial(null, true) === "sombre"` et `themeInitial("clair", true) === "clair"` ;
  - `messageProbleme(404) === "Contrat introuvable"` et `messageProbleme(429, "TROP_DE_REQUETES")` donne le texte du 429.
- [ ] **Step 2 : `node --test gateway/tests/espace/`.** Attendu : FAIL.
- [ ] **Step 3 : implémenter** `logique.js`, puis `auth.js`, `api.js`, `app.js` (routeur sur `hashchange`, rendu par `document.createElement` et `textContent`), `index.html` et `app.css` (variables de couleur sous `[data-theme=sombre]`, `:focus-visible` marqué).
- [ ] **Step 4 : `make espace-test` puis `make gateway-test`.** Attendu : PASS.
- [ ] **Step 5 : vérification manuelle locale** (`make up`, `http://localhost:8000/app/`), au clavier seul :
  - connexion A ;
  - passage des onglets aux flèches ;
  - ouverture d'un dossier avec Entrée ;
  - thème basculé, puis gardé après rechargement ;
  - une question au tchat rend une réponse et ses sources.

  Noter le résultat dans `docs/espace-gestionnaire.md` (§ Accessibilité, RGAA 11.1 / WCAG 2.1.1).
- [ ] **Step 6 : commit** `feat(espace): connexion A/B, onglets, thème, portefeuille et tchat (#103)`.

### Task 9 : page — dossier : lancer, frise, détail, pause/reprise, proposition, revue, contrat (#104)

**Files :**
- Modify : `wwwroot/app/{app.js, logique.js, app.css}`, `gateway/tests/espace/logique.test.mjs`

**Interfaces :**
- Consumes :
  - tâche 2 (`GET /api/contrats/{n}/etat`) ;
  - tâche 4 (`GET /v1/souscriptions/{n}/contrat`) ;
  - tâche 6 (`POST …/pause`, statut `EN_PAUSE`, `409 EVALUATION_EN_COURS`) ;
  - `GET /api/traces/{trace_id}` (existant) ;
  - `POST /v1/souscriptions/{n}/evaluation` et `…/revue` (existants, portée `cluster`).
- Produces (`logique.js`) :
  - `frise(etat, lanceA?: number) -> Array<{agent: "pieces"|"analyste"|"redacteur"|"actuaire"|"validation", libelle, statut: "fait"|"en_cours"|"a_venir", duree_s: number|null}>`. Libellés : Pièces, Analyste, Rédacteur, Actuaire, Validation (vous).
    - Durée d'un agent = écart de `cree_le` avec le rapport précédent.
    - Pour le premier agent, l'écart se mesure depuis `lanceA` (horodatage local du clic) ; sans `lanceA`, la durée est `null`.
    - « Validation » est `en_cours` si `statut_parcours == "EN_ANALYSE"`, `fait` si `ACCEPTE`/`REFUSE`.
  - `doitInterroger(statutReponse: string|null, enVol: boolean) -> boolean` : vrai tant que `POST …/evaluation` est en vol.
- Comportement :
  - **Lancer / Reprendre** fait `POST …/evaluation`. Le bouton est désactivé (`aria-disabled`) pendant l'appel. Pendant le vol, la page lit `GET …/etat` **toutes les secondes**, puis une dernière fois à la réponse.
  - **Pause** fait `POST …/pause` et n'est actif que pendant le vol ; à `EN_PAUSE`, le bouton principal devient « Reprendre ».
  - Temps écoulé affiché toutes les secondes ; `trace_id` du dernier rapport.
  - Clic sur une étape (bouton) : sous-onglet « Détail » avec mode, cause et les spans de sa trace (`GET /api/traces/{trace_id}` : nom du span et durée). On n'affiche que les noms d'outils (`execute_tool …`) et les garde-fous, jamais d'attribut libre.
  - Sous-onglet « Contrat proposé » : décision, `contrat_type`, `regle_ids`, motifs, citations, prime annuelle et mensuelle. Formulaire avec motif obligatoire (1 à 500 caractères) et boutons Valider (`ACCEPTE`/`VALIDEE`), Corriger (`ACCEPTE`/`CORRIGEE`) et Refuser (`REFUSE`/`VALIDEE`), qui envoient `POST …/revue`. En `REVUE_HUMAINE`, le message neutre de la réponse s'affiche.
  - Après `ACCEPTE` : `GET /v1/souscriptions/{n}/contrat`, affichage puis bouton « Imprimer » (`window.print()`, feuille `@media print`).

- [ ] **Step 1 : tests** `logique.test.mjs` :
  - `frise` sur un état à deux rapports espacés de 3,1 s donne les statuts `["fait","fait","a_venir","a_venir","a_venir"]` et `duree_s[1] === 3.1` ;
  - `frise` sur `statut_parcours: "EN_ANALYSE"` donne une validation `en_cours` ;
  - `frise({statut_parcours:null, rapports:[]})` donne tout `a_venir` ;
  - `doitInterroger(null, true) === true` et `doitInterroger("EN_PAUSE", false) === false`.
- [ ] **Step 2 : `make espace-test`.** Attendu : FAIL.
- [ ] **Step 3 : implémenter** `frise`, `doitInterroger`, puis la vue dossier dans `app.js`.
- [ ] **Step 4 : `make espace-test`.** Attendu : PASS.
- [ ] **Step 5 : vérification manuelle locale au clavier** (faux LLM du compose) : lancer, voir la frise avancer, mettre en pause, reprendre, valider, puis afficher et imprimer le contrat. Double clic sur Lancer : un seul appel part, sinon le message `409`. Noter le résultat dans `docs/espace-gestionnaire.md`.
- [ ] **Step 6 : commit** `feat(espace): évaluer, suivre, mettre en pause, valider et afficher le contrat (#104, #129, #101)`.

### Task 10 : page — pièces manquantes et relance modifiable (#130)

**Files :**
- Modify : `wwwroot/app/{app.js, logique.js}`, `gateway/tests/espace/logique.test.mjs`

**Interfaces :**
- Consumes : section `pieces` de `GET …/etat` (`{statut, manquantes: [str], note}`), `nb_relances`, et `POST /api/contrats/{n}/relances` de la tâche 3.
- Produces (`logique.js`) :
  - `LIBELLES_PIECES = {releve_information: "relevé d'information", permis: "permis de conduire", carte_grise: "certificat d'immatriculation"}`. Un type inconnu s'affiche tel quel.
  - `gabaritRelance(manquantes: string[]) -> string` rend exactement :
    ```
    Bonjour,

    Pour finaliser l'étude de votre dossier, merci de nous transmettre : <libellés joints par ", ">.

    Cordialement,
    ```
- Comportement :
  - Le sous-onglet « Pièces manquantes » porte une pastille avec le nombre de pièces, et seulement si `pieces.statut == "incomplet"`. Il affiche « Relance n/3 ».
  - Une `<textarea>` étiquetée est préremplie par `gabaritRelance`, avec `maxlength=4000`.
  - « Envoyer la relance » fait `POST …/relances {texte, pieces: manquantes}`. À la réponse 201 : message « Relance n/3 enregistrée (envoi par e-mail à partir du 15/11) ». À `409` : bouton désactivé, avec « 3 relances déjà envoyées ».
  - Le texte n'est jamais réinjecté par `innerHTML`.

- [ ] **Step 1 : tests** :
  - `gabaritRelance(["releve_information"])` contient `"merci de nous transmettre : relevé d'information."` ;
  - `gabaritRelance(["releve_information","x_y"])` contient `"relevé d'information, x_y."`.
- [ ] **Step 2 : `make espace-test`.** Attendu : FAIL.
- [ ] **Step 3 : implémenter.**
- [ ] **Step 4 : `make espace-test`.** Attendu : PASS. Vérification manuelle locale sur le dossier sans relevé : trois envois, puis le quatrième refusé ; un texte `<b>x</b>` s'affiche littéralement.
- [ ] **Step 5 : commit** `feat(espace): pièces manquantes et relance modifiable tracée (#130)`.

### Task 11 : infra, CI et documentation

**Files :**
- Modify : `infra/entra.sh`
  - l. 43 `redirections` : ajouter `"https://<gateway staging>/app/"` et `"https://<gateway production>/app/"`, construits à partir des variables du script ;
  - rôle `Gestionnaire` du cluster pour `DEMO_USER_ID`, s'il manque (cf. l. 117-150).
- Modify : `infra/containerapp.yaml` (env `Espace__Authority`, `Espace__Scopes__*`, `Espace__Comptes__A`, `Espace__Comptes__B`, sans secret)
- Modify : `.github/workflows/ci-cd.yml` : les variables `E2E_CONTRAT_*` restent, leurs valeurs changent côté GitHub.
- Modify : `e2e/test_cluster.py` : `test_pause_puis_reprise` (E2E, sauté en CI comme les autres tests OBO).
- Create : `docs/espace-gestionnaire.md` (usage, accessibilité, procédure de démo).
- Modify : `gateway/README.md` (§ `/app/`), `README.md` racine (lien), `docs/contrat-personnel.md` (K6 : preuve clavier).

- [ ] **Step 1 : E2E** `test_pause_puis_reprise` : avec `E2E_CLUSTER_INTERNE` et `E2E_CONTRAT_PROPRE`, `POST …/pause` → 202, puis `…/evaluation` → `EN_PAUSE`, puis `…/evaluation` → `EN_ANALYSE` ou `REVUE_HUMAINE`.
- [ ] **Step 2 : `make test` et `make lint`.** Attendu : PASS ; l'E2E est collecté, puis sauté sans environnement.
- [ ] **Step 3 : écrire `docs/espace-gestionnaire.md`.** Il contient : ce que fait chaque écran, la correspondance avec les routes, la checklist clavier (tâches 8-10), et les commandes que lance **Acerola**. Celles-ci, en bloc copiable :
  - `make entra DEMO_USER_ID=<oid de A>` ;
  - `gh variable set SEED_GESTIONNAIRE_A --body <oid de A>` ;
  - `gh variable set SEED_GESTIONNAIRE_C --body <oid de la CI>` ;
  - `gh variable set E2E_CONTRAT_PROPRE --body AIF-2026-000007` ;
  - `gh variable set E2E_CONTRAT_HOSTILE --body AIF-2026-000008` ;
  - le redéploiement de la base annexe (`docs/rollback.md`).
- [ ] **Step 4 : commit** `docs(espace): procédure de démo, accessibilité et réglages Entra (#38)`.
- [ ] **Step 5 : pousser `feat/GenererContrat` et ouvrir la PR en brouillon** vers `main` (« Closes #103, #104, #101, #122, #129, #130 ; partie de #38 et #100 »).

### Task 12 : preuve en staging — 3 dossiers de référence depuis l'espace (#100, manuel)

Après le déploiement en staging de la PR, et une fois les commandes de la tâche 11 lancées par Acerola.

- [ ] **Step 1 : vérifier la santé.** `GET /health/cluster` donne `garde_fous: prets` ; `GET /api/contrats` en A liste `000001`–`000003` (et `000010` s'il existe) ; en B, `000004`–`000006`.
- [ ] **Step 2 : jouer les 3 dossiers en A, depuis l'espace.**
  - `000001` : `EN_ANALYSE`, `ACCEPTE` proposé, `contrat_type` cité.
  - Dossier « refus » (tâche 1) : `REFUSE` proposé, `regle_id` cité ; dépend de #99, noter « en cours » s'il n'est pas livré.
  - `000003` : `REVUE_HUMAINE`, pièces manquantes (relevé) ; une relance envoyée.
  Une pause puis une reprise sur l'un des trois.
- [ ] **Step 3 : faire la revue de `000001`.** Valider, puis `GET /api/contrats/AIF-2026-000001` avant et après (K4), puis afficher le contrat.
- [ ] **Step 4 : relever les durées** de la frise et du temps total (< 30 s, K5) ; enchaîner deux évaluations sans 502 (#122).
- [ ] **Step 5 : écrire le rapport** `eval/preuves/parcours-2026-10-<jour>-staging.json` (requêtes, statuts, `trace_id`, durées ; aucune donnée personnelle). Passer K1 et K4 à « tenu » dans `docs/contrat-personnel.md` si c'est le cas.
- [ ] **Step 6 : commit** `docs(preuve): parcours « générer un contrat » joué en staging depuis l'espace (#100)`.
