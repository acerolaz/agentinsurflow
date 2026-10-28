# O1 — Instrumenter AgentInsurFlow vers Application Insights (#54)

*Spec de la session S1 du sprint 5 — 28/10/2026. Découpage : [`2026-10-28-sprint5-sessions.md`](2026-10-28-sprint5-sessions.md).*

## 1. Intention

Rendre le système **observable en staging et en production** dans Application Insights. C'est la base de tout le sprint : le tableau de bord (S2), les alertes (S2), la doc d'exploitation (S3) et la démo (S7) lisent ce que S1 émet. S1 clôt aussi la partie « collecteurs intégrés » de #54 et fournit les preuves KQL attendues par **K2** et **K9** (Application Map, Transaction Diagnostics, Live Metrics, KQL sur `audit.agent`).

Aujourd'hui, seuls les traces OTLP → référentiel SQL d'`underwriting-admin` et la Function de calcul (déjà sur App Insights) existent. La base annexe est éphémère : rien ne survit à une révision, et rien n'est requêtable en KQL.

## 2. Objectifs

1. Les **5 services** (gateway, agentic-cluster, rag, serveur-mcp, underwriting-admin) envoient leurs traces à **une ressource App Insights par environnement** (`appi-…-staging`, `appi-…-production`), en mode workspace, sur le Log Analytics existant (D-V1, D-V14).
2. La **Function de calcul** envoie vers la même ressource que son environnement, pour que l'**Application Map** relie gateway → cluster → MCP → rag / underwriting-admin / Function de bout en bout (`traceparent` propagé).
3. Le journal **`audit.agent`** arrive dans `AppTraces` (champs dans `Properties`), sans perdre sa sortie JSON sur stdout (utilisée en local).
4. Un nouvel événement **`audit.evaluation`** (D-V7) : une ligne par évaluation terminée, **tous chemins confondus** (succès, `REVUE_HUMAINE`, budget `duree`, `precondition`, erreur) : `trace_id`, `numero_contrat`, `duree_ms`, `statut_final`, `cause`. Requis par l'alerte A7 et la latence p95 par évaluation.
5. Un événement **`garde_fous.chargement`** au démarrage du cluster avec `chargement_ms` (D-V7, 💡 accepté — *mon choix* : une ligne, utile au dashboard et au diagnostic du démarrage à froid).
6. **Live Metrics** actif sur les services Python et C# (vecteur temps réel exigé par C11).
7. Les **requêtes KQL** du catalogue (`docs/contrat-personnel.md` §4) sont **exécutées en staging et corrigées** (noms de colonnes réels), puis consignées comme preuve.

## 3. Non-objectifs

- Tableau de bord, Action Group, règles d'alerte : **S2**.
- `docs/exploitation.md` : **S3**.
- Métrique OTel `gen_ai.client.token.usage` (histogramme) dans la gateway : **écartée** (décision du 28/10, option a). Les jetons restent des attributs de span.
- Mesure en ligne des faux positifs des garde-fous : reste hors ligne (`make garde-fous`).
- Checkpointer HTTP (D26) : **S4**.

## 4. Anti-objectifs (échec même si « ça marche »)

- Un **nom, une adresse, un prompt, une sortie de modèle, un texte d'observation ou un jeton** dans App Insights. Cela inclut les journaux applicatifs autres que l'audit, s'ils peuvent contenir de tels champs : le collecteur de journaux est **limité au journal `insurflow.audit`** (et à `garde_fous.chargement`), pas au journal racine.
- Le **numéro de contrat dans un chemin HTTP** des requêtes et dépendances : l'anonymisation existante (`anonymiser_requete`, gabarit `/evaluations/{numero_contrat}`) doit continuer de s'appliquer, y compris aux spans créés par l'instrumentation automatique du distro Azure Monitor.
- **Spans en double** : le distro instrumente FastAPI, requests, etc. ; il ne doit pas doubler l'instrumentation déjà en place.
- Une panne d'App Insights ou de l'export qui **bloque ou ralentit une réponse** (même règle qu'aujourd'hui pour l'OTLP).
- Le panneau **« Outils appelés »** de l'espace gestionnaire ou l'**E2E de la CI** qui cessent de fonctionner.
- Une p95 d'évaluation qui sort du budget (garde globale 25 s) à cause de l'export.

## 5. Contraintes

- Gel des fusions sur `main` du 29/10 au matin jusqu'à la fin de la démo du 30/10.
- Dépendances accordées le 28/10, **dernière version stable, figée** : `azure-monitor-opentelemetry` (rag, serveur-mcp, agentic-cluster ; `uv.lock`) et `Azure.Monitor.OpenTelemetry.AspNetCore` (gateway, underwriting-admin ; `.csproj`). Aucune autre montée de version.
- Toute écriture Azure (création des ressources App Insights, rebranchement de la Function, variables GitHub) est **dans un script lancé à la main par Acerola**.
- Hexagonal côté Python : la configuration du distro vit dans l'adapter existant `infrastructure/otel/telemetrie.py` de chaque service ; `audit.evaluation` passe par le port d'audit (`AuditPort`), pas par un import d'OpenTelemetry dans `application/`.
- RGPD : `enable_content_recording=False` conservé ; empreintes SHA-256 conservées.

## 6. Décisions prises (par Acerola, telles quelles)

| # | Décision |
|---|---|
| D-V1 | Une ressource App Insights par environnement, en mode workspace, sur le Log Analytics existant. Un seul workspace (créé par l'environnement Container Apps) pour staging et production → les requêtes filtrent par ressource (`_ResourceId`). |
| D-V3 | Ordre : local → staging → production (celui de `ci-cd.yml`). |
| D-V4 | Scripts `az` + `sh` dans `infra/`, cible `make`, lancés à la main. S1 crée `infra/vigie.sh` avec **la seule étape « App Insights »** ; S2 l'étend. |
| D-V14 | Les 5 services. |
| D-V15 | Coût : jetons × prix unitaire **paramétrable**. Déploiements Foundry vérifiés en **GlobalStandard** → valeurs initiales Global, en USD par million de jetons : gpt-4.1-mini **0,70 / 2,80** *(corrigé le 29/10 : **0,40 / 1,60**, compteurs `gpt 4.1 mini Inp/Outp glbl` de l'API des prix Azure ; 0,70 / 2,80 est le tarif `4.1 mini pp … Gl` des modèles fine-tunés)*, Kimi-K2.5 **0,60 / 3,00**. Taux USD → € : `🔴` (paramètre). Le calcul du coût est fait **en KQL** par S2 ; S1 garantit seulement que `modele`, `tokens_entree`, `tokens_sortie` sont requêtables. |
| 28/10 Q3 | Jetons de la gateway : **attributs de span** (`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.model`), lus en KQL. D-V8 devient : Σ journalière des attributs de la gateway (route `/api/llm`) cohérente avec Σ `tokens_entree + tokens_sortie` d'`audit.agent` (l'écart = rag) → preuve dans `eval/preuves/`. |
| 28/10 Q4 | `audit.agent` exporté par l'export OTel des journaux vers `AppTraces` ; le JSON sur stdout reste. |

## 7. D-V2 amendée (décidée par Acerola le 28/10 : solution a)

D-V2 disait « référentiel SQL des traces en local seulement ». Or l'espace gestionnaire (`gateway/.../wwwroot/app/dossier.js:115`) et l'E2E de la CI (`e2e/test_parcours.py:92`, `:172`) lisent `GET /api/traces/{trace_id}` en staging. **Double export en Azure** : chaque service envoie ses traces à App Insights **et**, comme aujourd'hui, au référentiel SQL. Rôles : le SQL sert l'espace gestionnaire, l'E2E et le local (exigence C20 « au minimum en local ») ; App Insights sert la vigie. La perte des traces SQL à chaque révision reste acceptée (déjà le cas).

## 8. Comportement attendu

**Choix de l'exportateur, par configuration** (même règle pour les 5 services) :

| Variable présente | Effet |
|---|---|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Export vers App Insights (traces, journal d'audit, Live Metrics) |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` (ou `_ENDPOINT`) | Export OTLP vers le référentiel SQL, comme aujourd'hui |
| les deux | double export (staging, production) |
| aucune | spans locaux, aucun export (tests) |

- Python : `configure_azure_monitor(...)` (≈ `builder.Services.AddOpenTelemetry().UseAzureMonitor()`), avec l'exportateur OTLP existant ajouté comme processeur de spans supplémentaire, le collecteur de journaux restreint à `insurflow.audit`, et l'anonymisation des chemins conservée.
- C# : `UseAzureMonitor()` en plus du `WithTracing(...AddOtlpExporter)` existant, quand la chaîne de connexion est présente. Le filtre `/health` de la gateway est conservé.
- Ressource OTel : `service.name` (nom actuel de chaque service → « rôle cloud » de l'Application Map), `service.version`, `deployment.environment`.

**Chaîne de connexion** : *mon choix* — une valeur par environnement GitHub (`staging`, `production`), injectée par `deploy.yml` comme les autres variables, en **secret de Container App** (`secretref`), selon les conventions de `docs/secrets.md`. Les fichiers `infra/containerapp*.yaml` la reçoivent ; ceux qui n'ont pas encore de variable OTLP gardent leur export actuel.

**`audit.evaluation`** : émis une fois par évaluation à sa fin, quel que soit le chemin (y compris budget épuisé `duree`, `precondition`, erreur MCP). `statut_final` ∈ statuts du cycle de vie (`ACCEPTE`, `REFUSE`, `REVUE_HUMAINE`, `PIECES_MANQUANTES`, …) ou erreur. Même format que `audit.agent` (JSON stdout + export OTel), mêmes règles RGPD. Points d'entrée repérés : `agentic-cluster/.../application/evaluation.py` et `infrastructure/langgraph/graphe.py` (`ServiceEvaluation`).

**`infra/vigie.sh` (étape App Insights)** — `make vigie ENV=staging|production`, idempotent comme `bootstrap.sh` (`existe … ||`) :
1. crée `appi-insurflow-<env>` (`az monitor app-insights component create --workspace workspace-svespucepZG6`) ;
2. rebranche la Function `acerolaz-calcul-<env>` sur cette ressource (§8 bis) ;
3. affiche la chaîne de connexion et la commande `gh variable set` / `gh secret set` **à lancer à la main**.

## 8 bis. Précisions issues de la relecture (28/10)

**Existant Azure** (lu en lecture seule le 28/10) :
- Log Analytics de l'environnement Container Apps `cae-insurflow` : **`workspace-svespucepZG6`** (svespuceRG) → c'est « le Log Analytics existant » de D-V1.
- La Function a déjà des App Insights **créés automatiquement** par `az functionapp create` : `acerolaz-calcul-staging` et `acerolaz-calcul-production`, en mode workspace mais sur **`DefaultWorkspace-…-SEC`** (`DefaultResourceGroup-SEC`), pas sur `workspace-svespucepZG6`.
- *Mon choix* : `vigie.sh` crée `appi-insurflow-staging` et `appi-insurflow-production` sur `workspace-svespucepZG6`, puis pose leur chaîne de connexion dans le réglage `APPLICATIONINSIGHTS_CONNECTION_STRING` de `acerolaz-calcul-<env>` (`az functionapp config appsettings set`). Les anciens composants ne sont **pas supprimés** (historique) ; leur suppression éventuelle revient à Acerola.

**Périmètre par service** (*mon choix*) :
- underwriting-admin reçoit la chaîne App Insights **et garde** son export OTLP vers son propre `/v1/traces` en localhost (existant, `Program.cs`) ; la route `/v1/traces` elle-même n'est jamais tracée (test existant). *(Corrigé au plan : cette ligne disait à tort « sans OTLP ».)*
- Gateway et underwriting-admin : le numéro de contrat (`AIF-AAAA-NNNNNN`) est masqué dans les attributs d'URL et le nom des spans HTTP, entrants et sortants. Cela clôt #65 : l'anti-objectif du §4 l'exige dès que ces spans partent vers App Insights.
- La gateway fait le double export : `UseAzureMonitor()` plus l'`AddOtlpExporter` existant, avec son jeton d'application.

**`audit.evaluation`** :
- Il ne compte que les évaluations **entrées dans la Saga**. Une requête rejetée en amont (401, 403, 404, 409, 422) n'est pas une évaluation : les tuiles et alertes de S2 la lisent dans `AppRequests`.
- Une évaluation qui échoue après son entrée reçoit `statut_final = "ERREUR"`, et sa cause technique va dans `cause`.
- `numero_contrat` est autorisé dans `Properties` : il est non identifiant (D-V15, Acerola), comme dans `audit.agent` aujourd'hui. Il reste interdit dans les chemins HTTP.

**Dépendances sortantes** :
- Aucun corps de requête ni de réponse n'est capturé : c'est le comportement par défaut d'OpenTelemetry, à ne pas modifier.
- Les instrumentations automatiques du distro sont **limitées à celles déjà utilisées par chaque service** (liste blanche).
- La preuve RGPD n° 7 couvre aussi les URL des dépendances (`AppDependencies`).

**Calendrier** (*mon choix*) :
- La PR S1 est fusionnée **après la démo du 30/10**.
- `make vigie ENV=…` (étape App Insights) peut être lancé avant, car il ne déploie rien. La preuve en staging suit la fusion, et la production vient ensuite, avant le 15/11.

**Porte des evals** : « inchangée » veut dire **la porte existante de `ci-cd.yml` reste verte**, avec une réussite ≥ 80 % et un p95 ≤ 30 s (D11). Le p95 obtenu est comparé aux 14,9 s du 27/10 et consigné, mais il ne bloque pas tant que la porte passe.

## 9. Preuves de fin de session (définition de « fini »)

En **staging**, après déploiement :
1. Application Map : gateway, agentic-cluster, serveur-mcp, rag, underwriting-admin et la Function **reliés** sur une évaluation.
2. Transaction Diagnostics : une évaluation de bout en bout, un seul `operation_Id`.
3. Live Metrics : le cluster visible pendant une évaluation.
4. Chaque requête KQL du catalogue (`docs/contrat-personnel.md` §4) **exécutée**, corrigée si besoin, et recopiée **validée** dans le contrat ; résultats dans `eval/preuves/kql-<date>-staging.md`.
5. `audit.evaluation` présent pour une évaluation nominale **et** pour une évaluation `llm-off` (`REVUE_HUMAINE`, cause `llm_ko`).
6. Preuve D-V8 (jetons gateway vs `audit.agent`) dans `eval/preuves/`.
7. RGPD : une requête KQL qui cherche les champs interdits (noms, e-mails, contenu) ne remonte rien ; consignée avec la preuve 4.
8. Panneau « Outils appelés » de l'espace et E2E de la CI toujours verts.
9. Porte des evals : p95 ≤ 30 s, réussite inchangée par rapport au 27/10 (p95 14,9 s).

Puis la même chose en **production** (preuves 1, 3 et 4 suffisent).

Tests : TU sur le choix de l'exportateur (4 cas du tableau), sur `audit.evaluation` (champs, chemins d'échec, absence de donnée personnelle) et sur l'anonymisation des chemins sous le distro. Le test de règle de dépendance existant doit rester vert.

## 10. Laissé au constructeur

- Les noms exacts des colonnes KQL (`Properties` vs `customDimensions`, `AppDependencies` pour les spans internes `invoke_agent`).
- Comment neutraliser les instrumentations automatiques du distro qui doubleraient l'existant.
- L'emplacement exact de l'émission d'`audit.evaluation` pour couvrir tous les chemins.
- Le taux d'échantillonnage (≈ 500 dossiers/jour : 100 % sans doute suffisant ; à justifier).
  - Décision du 28/10 : échantillonnage à 100 % (C# `SamplingRatio = 1` / `TracesPerSecond = null`, Python `OTEL_TRACES_SAMPLER=parentbased_always_on`). Justification : le fournisseur de traces partagé ferait aussi perdre des spans à l'export OTLP vers le référentiel SQL (D-V2).
- La mise à jour du commentaire périmé de `make up` dans le `Makefile`.
