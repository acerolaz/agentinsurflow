# Espace gestionnaire — démo « générer un contrat » (30/10)

*Conception du 27/10/2026 (brainstorming d'Acerola). Parapluie : #38. Répartition : #103, #104, #101, #100, #122, une nouvelle issue « pause », #123 (au 15/11). Maquette de référence : `.superpowers/brainstorm/…/espace-gestionnaire-v2.html` (non versionnée ; ses écrans sont décrits au § 4).*

## 1. Intention

Le 30/10, devant le jury, un gestionnaire se connecte, ouvre un dossier de son portefeuille et **lance le cluster d'agents** sur ce dossier. Il **suit** chaque étape (Pièces → Analyste → Rédacteur → Actuaire), voit le **détail** et la **durée** de chacune, peut **mettre en pause** puis **reprendre**, est **prévenu des pièces manquantes** et corrige le mail de relance, puis **valide** le contrat proposé et l'affiche. À côté, il **interroge le corpus** dans un tchat.

Pourquoi : c'est la preuve C10 (une application consomme l'API) et la preuve K1/K4 (#100) jouée sur le vrai corpus. Aujourd'hui, le parcours n'est visible que dans Swagger et dans les E2E sautés en CI.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs (tous pour le 30/10, décision d'Acerola)**
1. Connexion Entra en choisissant le gestionnaire **A** ou **B**. Chacun voit **son** portefeuille, rien d'autre.
2. Une SPA à onglets : **Mes dossiers** (liste, puis page du dossier) et **Tchat corpus**. Thème **clair/sombre** au bouton.
3. Page dossier : bouton **Lancer / reprendre**, **frise** des étapes avec la durée de chacune, le temps total et le `trace_id`. Un clic sur une étape montre son **détail** (mode `llm`/`regles`, outils appelés, sortie, garde-fous, cause).
4. **Pause après l'étape en cours**, puis **reprise** là où le workflow s'est arrêté.
5. **Pièces manquantes** : alerte, compteur de relances (n/3) et mail proposé **modifiable**. « Envoyer » **enregistre et trace** la relance comme envoyée, **sans e-mail réel**.
6. **Contrat proposé** : décision, formule, prime, `contrat_type` et `regle_id` cités. **Valider / Refuser** avec un motif. Après `ACCEPTE`, affichage et impression du **contrat** (#101).
7. **Tchat corpus** : une question, une réponse avec ses sources, par la route `agent` du RAG.
8. Parcours complet **au clavier** (K6, RGAA 11.1 / WCAG 2.1.1), focus visible, libellés.

**Non-objectifs (reportés au 15/11, #123)** : l'envoi réel du mail par ACS, le flux SSE (la progression se fait par interrogation périodique), l'orchestrateur LLM, `SANS_SUITE`.

**Anti-objectifs** (ce qui ferait échouer la démo même si tout « marche ») :
- Un gestionnaire voit ou agit sur un dossier de l'autre (BOLA).
- Le jury voit « Un service du cluster est indisponible » parce que deux dossiers ont été évalués coup sur coup (#122).
- Une donnée personnelle s'affiche dans le détail d'une étape ou part dans une trace.
- Un nouveau service public apparaît, ou un secret entre dans la page.
- L'agent écrit `ACCEPTE` sans le gestionnaire (A4 et K4 restent vrais).

## 3. Contraintes

- **Stack de l'interface (décision d'Acerola, écart au « Swagger seul » de `brief2/prompt.md` L3)** : page **HTML + JavaScript sans étape de build**, **servie par la gateway** (fichiers statiques), connexion par **MSAL.js** (code + PKCE). Pas de framework, pas de npm. La gateway reste la **seule entrée publique**.
- Monorepo (`CLAUDE.md` racine) : Python hexagonal, C# Clean Architecture, ProblemDetails avec un `code`, OpenAPI dans la page Swagger unique, chaque service **revalide** le jeton, écritures Azure/Entra rédigées dans `infra/*.sh` et **lancées à la main par Acerola**, aucun secret, français partout.
- Le cluster n'est joint qu'en **OBO** d'un compte humain ; la page envoie un jeton utilisateur à la gateway, qui ne change rien à la chaîne existante.
- Les versions (`pyproject.toml`) ne bougent pas sans accord d'Acerola.
- Les tests suivent `.claude/rules/testing-pyramid.md` : chaque test annonce son niveau.

## 4. Ce qui a été décidé, par point et par issue

| # | Point | Issue | Décision |
|---|---|---|---|
| 1 | Connexion A/B, portefeuille, dossier, onglets, thème | **#103** | SPA servie par la gateway. Écran de connexion : deux cartes « Gestionnaire A » et « Gestionnaire B ». Le choix ne fait que **préremplir l'identifiant** (`loginHint`) pour MSAL ; l'identité réelle vient d'Entra, jamais du choix. Thème mémorisé dans `localStorage`, préférence système par défaut |
| 2 | Tchat corpus | **#103** (ajout) | Écran « Tchat corpus » qui appelle la route `agent` du RAG par la gateway (rôle `Gestionnaire`) ; réponses avec sources cliquables |
| 3 | Lancer, proposition, Valider/Refuser | **#104** | Inchangé par rapport à l'issue |
| 4 | Contrat généré | **#101** puis **#104** | Inchangé |
| 5 | Progression, durée, détail des étapes | **#104** (ajout) | Lecture de l'état du dossier (sections et `RAPPORT_AGENT` : agent, tentative, mode, cause, `trace_id`, horodatage), interrogée **chaque seconde** pendant une évaluation. Durée d'une étape = écart entre horodatages. Le flux SSE de #123 la remplacera |
| 6 | Pause entre les étapes, reprise | **nouvelle issue** (sous #7) | Une **demande de pause** enregistrée pour le dossier ; la Saga la consulte **après chaque `pas()`** et s'arrête alors sur un `interrupt()` de pause, distinct de celui de la validation. « Reprendre » relance au **point de reprise** LangGraph (déjà persistant, K11) |
| 7 | Pièces manquantes, mail modifiable | **nouvelle issue** (sous #7), ACS reste dans #123 | L'agent Pièces fournit la liste manquante ; la page propose un mail modifiable. « Envoyer » enregistre le texte, incrémente le compteur (max 3, D75) et écrit une trace « relance envoyée ». Aucun e-mail ne part avant le 15/11 |
| 8 | Deux gestionnaires humains | **#100** | **Décision d'Acerola (27/10)** : A devient le **second compte humain** (`DEMO_USER_ID` d'`infra/entra.sh`, rôle `Gestionnaire` sur rag, underwriting, mcp et cluster ; à ajouter pour le cluster s'il manque) et son oid devient `SEED_GESTIONNAIRE_A`. La CI passe sur un **3e gestionnaire C** ajouté au seed (`SEED_GESTIONNAIRE_C`, 3 dossiers synthétiques à partir de `000007`) ; ses variables `E2E_CONTRAT_PROPRE` / `E2E_CONTRAT_HOSTILE` / `E2E_CONTRAT_AUTRE` pointent vers C et un contrat d'un autre gestionnaire. La base annexe étant éphémère, on la ressème. Variables GitHub et `make entra` : lancés par Acerola |
| 9 | 502 sur évaluations rapprochées | **#122** | À corriger avant le 30/10 : une 429 d'un outil remonte en 429 lisible, et/ou les limites de débit sont dimensionnées pour une évaluation complète |
| 10 | Preuve K1/K4 | **#100** | Jouée **depuis l'interface**, sur les 3 dossiers de référence ; le rapport va dans `eval/preuves/` |

**Écrans** (maquette v2) :
- **Connexion** : deux cartes A/B, bouton « Se connecter avec Microsoft ».
- **En-tête** : onglets Mes dossiers / Tchat corpus, nom du gestionnaire, bouton thème, déconnexion.
- **Portefeuille** : tableau numéro / client / statut ; une ligne s'ouvre au clavier.
- **Dossier** : titre, boutons Pause et Lancer/Reprendre, temps écoulé, `trace_id`, frise de 5 étapes (la dernière : « Validation (vous) »), puis trois sous-onglets : *Détail de l'étape* · *Pièces manquantes* (pastille avec le nombre) · *Contrat proposé*.
- **Tchat** : fil question/réponse, sources sous chaque réponse, champ de saisie.

## 5. Existant constaté (main 0255717) et choix de Claude

**Existant** (relevé du 27/10, routes de `gateway/.../appsettings.Routes.json`) :
- Portefeuille et dossier : `GET /api/contrats`, `GET /api/contrats/{n}`, `GET /api/contrats/{n}/pieces`, `PUT …/observations` (politique `underwriting-gestionnaire`, BOLA déjà testé).
- Évaluation et revue : `POST /v1/souscriptions/{n}/evaluation` et `…/revue` (cluster, OBO, `cluster-gestionnaire`). L'évaluation est **synchrone** (≤ 25 s + réserve).
- Tchat : `POST /api/reponses` (RAG, `rag-gestionnaire`) existe déjà par la gateway : **aucune route à ajouter**.
- Détail d'une étape : `GET /api/traces/{trace_id}` (référentiel des traces, spans d'outils) existe déjà.
- **Manque** : une lecture de l'état du dossier (`ETAT`, `SECTION_ETAT`, `RAPPORT_AGENT`) ; seule l'écriture `PUT …/etat` (réservée au MCP) existe.
- Entra : `infra/entra.sh` gère déjà un **2e gestionnaire humain** (`DEMO_USER_ID`) et des `spa.redirectUris` ; il suffit d'y ajouter l'URI de la page (gateway de staging) et de le relancer.
- Seed : A possède `000001`–`000003`, B `000004`–`000006` ; le **dossier 3 est sans relevé** (`SeedDossiers.DossierSansReleve`).

**Choix de Claude** (minimes, à contester en relisant) :
- **Lecture de l'état** : `GET /api/contrats/{n}/etat` dans underwriting-admin (même BOLA `404`, liste blanche de champs : agent, tentative, mode, cause, `trace_id`, horodatage, sections sans donnée personnelle). Pas de route gateway nouvelle : `underwriting-contrats` la couvre déjà.
- **Détail d'étape** : rapport de l'agent + spans de sa trace (outils appelés, garde-fous) ; aucune sortie brute du LLM affichée, seulement les sections déjà minimisées.
- **Pause / reprise** : `POST /v1/souscriptions/{n}/pause` enregistre la demande ; l'évaluation en cours rend alors **200 avec statut `EN_PAUSE`** à la fin de l'étape courante. « Reprendre » rappelle **`…/evaluation`**, qui repart du point de reprise. Le drapeau vit avec l'état du dossier (port côté cluster, stockage dans le checkpointer, pas de nouveau service). Pendant l'appel, la page interroge `…/etat` chaque seconde.
- **Relance** : mail issu d'un **gabarit fixe** rempli avec les pièces manquantes de la section `pieces` ; le gestionnaire le modifie ; `POST /v1/souscriptions/{n}/relances` l'enregistre dans underwriting-admin (texte gardé avec le dossier, qui contient déjà les données du client) et **la trace ne porte que** « relance n/3 » et le type de pièce, jamais le texte. Le maximum de 3 est appliqué par le serveur (`409` au-delà).
- **MSAL.js** : fichier `msal-browser.min.js` **versionné dans le dépôt** (version figée, empreinte SRI), CSP stricte servie par la gateway (`script-src 'self'`). Pas de CDN.
- **#122** : d'abord confirmer la cause par les traces (case déjà prévue) ; quelle qu'elle soit, une 429 d'un outil remonte en **429 `TROP_DE_REQUETES` avec `Retry-After`**, et les limites de la gateway sont dimensionnées pour **deux évaluations complètes par minute et par gestionnaire**.
- **Tchat** : sources affichées en référence texte (titre, article) avec lien Légifrance quand l'extrait en porte un.
- La page statique n'apparaît pas dans l'OpenAPI ; seules les routes de données y figurent.

## 6. Laissé au constructeur

- Le découpage exact des nouvelles routes (cluster ou underwriting-admin) et leurs chemins publics `/v1/…` sur la gateway, du moment que chaque route revalide le jeton, filtre par portefeuille et figure dans l'OpenAPI.
- Le nom et la forme du drapeau de pause et de la trace de relance, dans le respect de l'hexagonal (port côté domaine, adaptateur côté infrastructure).
- L'organisation des fichiers statiques dans la gateway et la configuration MSAL (ID d'application, URI de redirection) fournie par la configuration, sans secret.
- Le dossier « refus » parmi les contrats du seed (ajuster ses données synthétiques si aucun n'est refusé par le barème), le dossier 1 restant « acceptable » et le dossier 3 « sans relevé ».
- Le niveau et le nombre des tests, dans les limites de la pyramide.
