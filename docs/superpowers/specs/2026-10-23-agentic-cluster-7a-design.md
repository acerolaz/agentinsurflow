# Cluster d'agents 7a et garde-fous — conception

*Issue #7 (lot 7a) · Sprint 4 « La composante agentique & les garde-fous » · jalon : examen blanc du 30/10 · branche `feat/cluster`*

> **Le dossier de conception fait foi** (`brief4/dossier-conception-v1.pdf`, V2.13 et addenda du 22/10 et du 23/10). Cette spec ne recopie pas le dossier : elle fixe le **périmètre 7a**, les **avenants** décidés le 23/10 et ce qui manque dans le code. En cas de contradiction, le dossier l'emporte, sauf pour les avenants listés en § 3.

## 1. Intention

Mettre **en production** la composante agentique gelée au sprint 1 — le microservice `agentic-cluster` (D105) : orchestrateur LangGraph, fabrique `SPECS`, quatre agents LangChain `create_agent` (📎 Pièces, 📏 Analyste, ⚡ Rédacteur, 💶 Actuaire), état du dossier, porte HITL — **protégée par des garde-fous d'entrée et de sortie** que l'évaluateur du sprint 4 éprouve **en live** avec ses propres prompts hostiles (injection, hors-périmètre, extraction de données).

Pourquoi maintenant : le brief Sprint 4 exige « la composante en production, garde-fous actifs » et l'état du contrat personnel versionné ; l'examen blanc du 30/10 exige un dossier qui traverse les quatre agents en plan de référence (addendum § 10.3).

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs (7a)**
- O1 — `agentic-cluster` en production (Container App, entrée interne, n'accepte que la gateway, D105), avec le **plan de référence** `prochaine_etape(etat)` comme orchestrateur (dossier § 4.5.6, sans LLM d'orchestrateur), les quatre agents avec leur LLM, leur référence ⓪, leur garde-fou ⑥ et leur repli ⑦ (dossier L4 bis).
- O2 — **Garde-fous d'entrée** : injection de prompt, hors-périmètre, PII, secrets — sur le texte non fiable qui entre dans un contexte LLM (§ 5.1).
- O3 — **Garde-fous de sortie** : GP1→GP4, GR1→GR3, GF1→GF7, GA1→GA3 (dossier, addendum § 3.4), **complétés** par LLM Guard (fuite de PII, secrets) ; refus poli, journalisé (§ 5.2).
- O4 — **Action sensible confirmée** : toute décision qui requiert le gestionnaire passe par `interrupt()` puis `POST …/revue` (K4) ; périmètre d'accès appliqué par la matrice `azp` × outil du serveur MCP et le portefeuille, journalisé (K3).
- O5 — `docs/contrat-personnel.md` : K1→K11, chacun **tenu / en cours / avenant**, avec sa preuve.
- O6 — Signaux à surveiller au sprint 5, listés dans ce même document (§ 8).

**Non-objectifs (7b ou ailleurs)**
- Orchestrateur LLM (GO1→GO3 sur un LLM, refus renvoyés au LLM) : **7b**. En 7a, GO1/GO2 existent comme code et sont testés avec un LLM simulé saboteur, mais l'orchestrateur en production est le plan de référence (coupe n° 3 du § 10.4 assumée pour le 30/10).
- `envoyer_relance` réel, e-mail ACS, `SANS_SUITE`, SSE `…/evaluation/stream` : **7b**.
- Interface gestionnaire (#38) : **hors de ce chantier**. La démo passe par Swagger / `curl` via la gateway.
- Générateur de dossiers (#49), correction des evals (#50) : chantiers séparés ; ce chantier s'appuie sur les seeds existants si #49 n'est pas prêt.
- Filtre de contenu natif d'Azure AI Foundry : non compté comme garde-fou ; cité en défense en profondeur dans la doc.

**Anti-objectifs** (échec même si « ça marche »)
- Un LLM qui voit le nom, le prénom, l'adresse, le numéro de permis ou une pièce (K2, D31, D39).
- Une décision `ACCEPTE`/`REFUSE` enregistrée sans validation du gestionnaire (K4).
- Un prompt hostile qui **change la proposition** (décision, prime, statut) par rapport au plan de référence : le code tranche, toujours (mode 😈 « injecte », dossier § 4b.4).
- Un refus qui révèle à l'appelant quel détecteur l'a déclenché ou qui renvoie une donnée du dossier.
- Une PII, un jeton ou le contenu d'un prompt dans une trace ou dans `audit.agent` (D91, D102).
- Un appel direct du cluster vers un autre service ou une base, hors checkpointer `agent_state` (D22, D26).
- Des faux positifs non mesurés : un garde-fou qui bloque tout « passe » la démo hostile mais échoue au critère « les usages légitimes passent ».

## 3. Décisions

### 3.1 Avenants décidés par Acerola le 23/10 (à reporter au journal des décisions, numéros 🔴 à attribuer)

| # | Décision | Amende |
|---|---|---|
| A1 | **Champ libre « observations du gestionnaire »** sur `CONTRAT` (texte, longueur bornée), saisi par le gestionnaire. C'est **le** champ libre visé par G-01. Il est transmis au **Rédacteur seul**, dans sa vue, balisé `<donnees_non_fiables>`, **après** le garde-fou d'entrée. | tranche P12 ; amende D39 (vue minimisée) |
| A2 | **LLM Guard** (Protect AI) est le SDK de garde-fous, **à l'intérieur** des middleware prévus par D96 : scanners d'entrée dans `GardeEntree` (`before_agent`), scanners de sortie dans `GardeSortie` (`after_agent`), à côté des fonctions pures GP/GR/GF/GA et du `PIIMiddleware`. | complète D96 |
| A3 | Les garde-fous d'entrée s'exécutent **dans `agentic-cluster`**, au chargement du dossier (`charger`, harnais, 0 LLM), **avant tout appel LLM** de l'évaluation. `underwriting-admin` accepte la saisie telle quelle. | — |
| A4 | L'**action sensible** à confirmer = toute décision qui requiert le gestionnaire : le brouillon (fiche + prime) attend `POST …/revue` derrière `interrupt()`. Pas de confirmation supplémentaire en 7a. | confirme K4, D9 |
| A5 | Le **refus** est un message **neutre** pour l'appelant ; la cause détaillée part dans `audit.agent` (sans PII). | précise D91 |
| A6 | L'orchestrateur du dossier s'appelle **Saga** (24/10) : automate déterministe (`prochaine_etape`, `precondition`) qui délègue aux sous-agents et écrit l'état, **sans rôle LLM**. Identifiant `saga` dans le code et la matrice MCP ; l'inscription Entra et les variables gardent `orchestrateur`. | renomme l'orchestrateur |

### 3.2 Ce que le dossier impose et que cette spec applique (rappel, pas avenant)

- Un garde-fou violé ⇒ **repli de l'agent** (référence + texte type) ou, pour le Rédacteur et pour l'entrée, **`REVUE_HUMAINE` avec le score du barème et la cause `garde_fou:<code>`** (dossier § 4.5.4, K5, chemin d'échec GF2). **Pas de 422** : le dossier ne prévoit pas de rejet HTTP d'une évaluation pour cause de contenu.
- PII : `PIIMiddleware(..., strategy="block")` (addendum § 7.4) — **bloquer, pas anonymiser**. Éval G02 : 0 PII dans un prompt ou une trace.
- Injection : **neutralisée** (G01 : 100 %) par trois couches — balisage `<donnees_non_fiables>`, sortie structurée `response_format` en liste fermée, référence déterministe qui fait foi — et, avec A2, **détectée** par LLM Guard.
- L'orchestrateur est le seul rédacteur de `EtatDossier` ; les agents rendent un rapport typé (D89) ; l'état long terme est écrit par `enregistrer_etat` dans `underwriting-admin` (D100) ; le checkpointer `PostgresSaver` dans `agent_state` (D93).
- Observabilité : Application Insights seul, `enable_content_recording=False`, un `audit.agent` par exécution d'agent (D90, D91, D102).
- Architecture hexagonale Python (règle utilisateur) ; le domaine (état, `SPECS`, `prochaine_etape`, `fusionner`, préconditions, garde-fous purs) n'importe ni LangGraph, ni LangChain, ni LLM Guard.
- Évaluation **synchrone en V1, ≤ 30 s** (L6.3) ; `thread_id = numero_contrat` (D93).
- **Le cluster joint le serveur MCP par la gateway** (`${GATEWAY_URL}/mcp`, route `mcp` existante), jamais par l'URL interne du serveur MCP ; de même pour `/api/llm` (D22, D105 ; précisé par Acerola le 23/10).

### 3.3 Précisions issues de la relecture (★ = choix de Claude, à vérifier par Acerola)

| Question | Réponse | Origine |
|---|---|---|
| Comment chaque agent obtient-il un jeton portant **son** `azp` ? | **Une inscription Entra par agent** (`orchestrateur`, `pieces`, `analyste`, `redacteur`, `actuaire`), chacune avec un **identifiant fédéré sur l'identité managée du cluster** (zéro secret en Azure ; secret dans `.env` en local, comme `rag`) ; le cluster fait un **OBO par agent** à partir du jeton du gestionnaire reçu de la gateway. Pré-autorisation des clients OBO sur l'API MCP et `identifierUris` `api://<appId>` (#47). Le serveur MCP lit déjà `MCP_AZP_*` (attendu « après #7 »). | D67, #15, #47 |
| Que renvoie un dossier bloqué à l'entrée, et d'où vient son score sans LLM ? | **Toute l'évaluation passe en repli** (aucun LLM appelé) : le plan de référence exécute les **références** ⓪ de 📎 Pièces et 📏 Analyste, chacune avec son propre `azp` (la matrice reste intacte : `evaluer_risque` appartient à l'Analyste), puis `orienter_revue_humaine(garde_fou:entree)` avec le score. Les rapports sont tracés `mode = repli`, cause `garde_fou:entree:<scanner>`. ★ | A3, K5 |
| Un hostile bloque-t-il seulement le Rédacteur ? | Non : toute l'évaluation (ligne ci-dessus). Les observations ne sont transmises qu'au Rédacteur, mais le contrôle est fait une fois, au chargement. | A1, A3 |
| `/revue` sans thread en pause, ou nouvelle évaluation sur un thread en pause ? | `/revue` sans `interrupt()` en attente ⇒ `409` ProblemDetails (`code` stable) ; `POST …/evaluation` sur un dossier dont un brouillon attend la revue ⇒ `409`. ★ | — |
| Qui écrit les observations, quand ? | Le gestionnaire du portefeuille (sinon `404`), tant que le dossier n'est pas décidé (`CONTRAT.statut` ∉ {`ACCEPTE`, `REFUSE`} ; avenant du 24/10 : le statut `actif` du seed est accepté) ; la valeur est **écrasée** (pas de version) ; l'évaluation lit la valeur courante ; un brouillon déjà produit n'est pas invalidé. Empreinte SHA-256 des observations évaluées dans `RAPPORT_AGENT`/`audit.agent`, pour l'audit. ★ | — |
| Si 100 % d'hostiles neutralisés et 0 % de faux positifs sont incompatibles ? | **G01 prime** : il est bloquant (L7.2) ; le taux de faux positifs mesuré est consigné dans `contrat-personnel.md` comme écart. Le jeu de prompts est écrit par Claude (décision d'Acerola), revu par Acerola ; l'évaluateur apporte les siens en live. Un scanner trop bruyant en français peut être remplacé par une règle pure, consigné. | L7.2, décision du 23/10 |
| Démarrage à froid de LLM Guard dans les 30 s ? | Modèles pré-téléchargés dans l'image et chargés **au démarrage** du conteneur (pas à la requête) ; sonde de disponibilité qui attend leur chargement ; `minReplicas = 1`. ★ | budget § 4.9 |

## 4. État du code et écarts à combler

Constaté sur `main` (v0.6.0, 23/10) :

| Élément | Existe | À faire en 7a |
|---|---|---|
| `agentic-cluster` | ❌ (aucun dossier) | Nouveau service Python, même gabarit que `serveur-mcp` (hexagonal, OBO, OTel, Dockerfile) |
| Serveur MCP — matrice | `orchestrateur`, `redacteur`, `actuaire` ; 6 outils ; `evaluer_risque` attribué à l'orchestrateur | Ajouter les `azp` **`pieces`** et **`analyste`** ; attribuer `evaluer_risque` à **Analyste** au lieu de l'orchestrateur (dossier L6.4) — il **reste un outil MCP** (via `/api/calcul`), seule la ligne de la matrice change ; ajouter **`lister_pieces`** (📎) et **`enregistrer_etat`** (🧭) |
| Entra ID | inscriptions orchestrateur, rédacteur, actuaire | Inscriptions `pieces`, `analyste` ; API **`api://agentic-cluster`** (pré-autorisation de la gateway, même modèle que #47) |
| Gateway | routes MCP, LLM, calcul, dossiers | Routes `/v1/souscriptions/{id}/evaluation` et `/revue` → cluster (échange de jeton, aud `api://agentic-cluster`) ; route d'écriture des observations ; allow-list `azp` pour `pieces`, `analyste` |
| `underwriting-admin` | `GET /api/contrats`, `PUT …/brouillon`, `PUT …/statut` ; entité pièces dans le MCD | Colonne `observations` sur `CONTRAT` + route d'écriture (portefeuille) ; tables `ETAT_DOSSIER`, `SECTION_ETAT`, `RAPPORT_AGENT`, `TOUR_PILOTAGE` (`RELANCE` en 7b) ; lecture des métadonnées de pièces pour `lister_pieces` |
| Infra | `containerapp-*.yaml` par service | `containerapp-cluster.yaml`, identité managée propre, entrée interne ; pipeline CI/CD étendu |

## 5. Garde-fous

### 5.1 Entrée — dans `charger` (harnais) puis `GardeEntree`

| Menace (OWASP LLM 2025) | Surface | Détecteur | Si détecté |
|---|---|---|---|
| LLM01 injection | `observations` | LLM Guard `PromptInjection` | `orienter_revue_humaine(garde_fou:entree)` + score du barème ; aucun LLM appelé |
| Hors-périmètre | `observations` | LLM Guard `BanTopics` (sujets hors souscription auto) | idem |
| LLM02 PII saisie | `observations` | LLM Guard `Anonymize`/détection PII **en mode détection** + `PIIMiddleware(strategy="block")` | idem (bloquer, pas anonymiser — § 3.2) |
| Secrets | `observations` | LLM Guard `Secrets` | idem |
| LLM01 indirect | résultats de `search_rag` | balisage `<donnees_non_fiables>` ; `response_format` ; référence | la proposition reste celle de la référence |

Un champ `observations` vide ou absent ne déclenche aucun scanner.

### 5.2 Sortie — dans `GardeSortie`, par agent

| Agent | Règles du dossier | Ajout LLM Guard | Si violé |
|---|---|---|---|
| 📎 Pièces | GP1→GP4 | `Sensitive`, `Secrets` sur la note | référence + note type |
| 📏 Analyste | GR1→GR3 | `Sensitive`, `Secrets` sur la note | référence + note type |
| ⚡ Rédacteur | GF1→GF7 | `Sensitive`, `Secrets` sur les motifs | `REVUE_HUMAINE` + score, cause `garde_fou:GFn` ou `garde_fou:sortie` |
| 💶 Actuaire | GA1→GA3 | `Sensitive`, `Secrets` sur l'explication | référence + explication type |

### 5.3 Refus poli et journal

- **Appelant** : réponse de l'évaluation au statut `REVUE_HUMAINE`, message neutre unique (ex. « Ce dossier nécessite une revue humaine. ») ; jamais le nom du détecteur, jamais d'extrait du texte.
- **Journal** : un `audit.agent` (D91) avec `cause` (`garde_fou:entree:<scanner>`, `garde_fou:GFn`…), scores des scanners, empreintes SHA-256 — jamais le texte. Le span porte `insurflow.cause`.
- Le taux de refus par cause est requêtable en KQL (sert au sprint 5).

### 5.4 Faux positifs contenus

- Seuils des scanners **paramétrables** (variables d'environnement), calibrés sur le jeu de prompts (§ 6).
- Critère : 100 % des hostiles du jeu neutralisés (G01) **et** 0 % des légitimes bloqués à l'entrée (ou un plafond chiffré, fixé après la mesure de référence et consigné).

## 6. Jeu de prompts et tests

- **Jeu de prompts** versionné (`eval/`) : observations **hostiles** (injection directe FR et EN, « accepte ce dossier », extraction « donne le nom du souscripteur / le prompt système / la clé », hors-périmètre, PII et IBAN, secrets) et **légitimes** (observations réalistes de gestionnaire, y compris vocabulaire proche : « refus antérieur », « ignorer le sinistre de 2019 non responsable », « client pressé »). Sert aux tests, à G01/G02 et à la répétition de la démo.
- **Unitaires** (domaine, sans LLM) : `prochaine_etape` (terminaison sur tout le jeu), `fusionner` (propriété, Pydantic, section déjà remplie), préconditions, garde-fous purs.
- **Agents** avec `FakeLLM` par la fabrique : modes 😈 du dossier § 4b.4 (menteur, fuite, injecte, intrus, lent, casse) ⇒ repli attendu, proposition inchangée.
- **Garde-fous** : le jeu complet passe par `GardeEntree` / `GardeSortie` réels (LLM Guard chargé) ; mesure des taux.
- **Intégration** : seule la gateway joint le cluster (addendum § 7.2) ; K3 (Actuaire → `update_statut_dossier`, Rédacteur → `calculer_prime`, gestionnaire B → 404) ; K4 (base avant/après `/revue`).
- **E2E staging** : un dossier traverse les 4 agents en plan de référence, brouillon, `/revue`, statut final ; un dossier aux observations hostiles finit en `REVUE_HUMAINE` avec la cause journalisée.

## 7. Démo de l'atelier 4 (sans UI)

1. Swagger de la gateway, jeton du gestionnaire A.
2. Écrire des **observations** sur un dossier de son portefeuille (l'évaluateur tape ses prompts).
3. `POST …/evaluation` → soit fiche + prime en brouillon (légitime), soit `REVUE_HUMAINE` + message neutre (hostile).
4. Montrer la cause dans App Insights (`audit.agent`, KQL) et l'absence de PII.
5. `POST …/revue` → statut final ; base consultée avant/après (K4).
6. Jetons de l'Actuaire, du Rédacteur, du gestionnaire B → `UNAUTHORIZED_TOOL` / 404 (K3).

## 8. Livrables documentaires

- `docs/contrat-personnel.md` : K1→K11, statut **tenu / en cours / avenant**, preuve (fichier, commande, endpoint, requête KQL), avenants A1→A5. Écarts connus à y porter : K2 vérifié par KQL (Langfuse supprimé, D103) ; K6 sans UI (#38) ; K8, K10 en 7b.
- Section **Sprint 5 — signaux à surveiller** : latence p95 par agent et par évaluation (budget 30 s), coût et jetons par dossier et par agent (SLO-6), taux de repli et de `REVUE_HUMAINE` par cause (SLO-5), taux de refus des garde-fous d'entrée et de sortie, taux de faux positifs sur le jeu légitime, erreurs (`llm_ko`, disjoncteur, `budget`), temps de chargement de LLM Guard (démarrage à froid).
- Avenants A1→A5 reportés au journal des décisions et dans le README.

## 9. Laissé au constructeur

- Découpage des modules à l'intérieur de l'hexagone (où vit le graphe LangGraph, nommage des adapters), tant que le domaine reste pur.
- Modèles LLM Guard en ONNX ou PyTorch, pré-téléchargés dans l'image ; ressources de la Container App (mémoire, `minReplicas`).
- Valeurs initiales des seuils, avant calibration.
- Longueur maximale de `observations`.
- Ordre des PR, à condition que chaque PR laisse `main` déployable.

## 10. Points ouverts — non tranchés (🔴 À CONFIRMER, aucune recommandation)

P5 seuil de pertinence · P13 contrat type par formule (GF6) · P14 budgets et top-k · P17 détail des facteurs de prime · P18 champs de `PRIME` et catalogue des outils · P23 colonnes de relance sur `CONTRAT` · P24 pièces exigées par formule · P31 rétention de `audit.agent` · P45 écarts production/dossier · clé pivot `numero` / `numero_contrat`.
