# Rapport E2 (C6, C7, C8) : veille, benchmark et paramétrage de Foundry

*03/11/2026. Soutenance le 12/11/2026. Rédigé après échange avec Acerola. Chaque choix est marqué **[Acerola]** (décidé par lui) ou **[Claude]** (proposé, à vérifier à la relecture).*

## 1. Intention

Acerola passe l'épreuve **E2** : un cas pratique, évalué sur un rapport professionnel individuel et une soutenance orale. Il lui faut un PDF de la même famille que `Exam/E1-rapport.pdf` et `Exam/E3-rapport.pdf`, qui présente **ce qui a réellement été fait** et comble honnêtement ce qui manque.

La veille existe mais n'est pas formalisée. **Le benchmark n'existe pas** : `specs/10-annexes.md` n'est qu'un gabarit de « ? ». Le paramétrage de Foundry est fait et documenté. La priorité du travail est donc C7.

## 2. Objectifs

1. `E2-rapport.pdf` et sa source Markdown, 15 à 20 pages (`Certif_Livrables.xlsx` : « LIVRABLE E2 - 15-20 pages - 15 minutes de présentation ») **[Acerola : format PDF inspiré de E1 et E3]**.
2. Un vrai benchmark de services d'IA, avec des mesures produites sur `svespuce-971`.
3. Une veille formalisée, avec des sources qualifiées, sur le thème validé.
4. Chaque critère de C6, C7 et C8 relié à une preuve dans une matrice.
5. `E2-support.md` : support de présentation de 15 min, sur le modèle de `E1-support.md` **[Acerola]**.

## 3. Non-objectifs

- Changer les modèles du projet : le benchmark recommande, Acerola décide ensuite par une PR séparée.
- Ajouter des fonctionnalités à l'application.
- Passer les déploiements en Data Zone dans ce travail : le rapport le recommande si besoin, Acerola décide ensuite (§6.2).

## 4. Anti-objectifs : ce qui ferait échouer le rapport même bien présenté

- **Une preuve inventée ou reconstituée** **[Acerola : « tu n'inventes rien : tu demandes »]**. Preuve absente : `🔴 À CONFIRMER`, ou question à Acerola.
- **Présenter le benchmark comme antérieur au choix.** Foundry et les modèles ont été choisis avant : le benchmark confirme ou contredit a posteriori, et le rapport le dit.
- **Antidater la veille** ou écrire « chaque dimanche » sans nuance (voir §6.1).
- **Un chiffre de benchmark qui n'a pas été mesuré**, ou un impact environnemental estimé sans source.

## 5. Contraintes

- **Écritures Azure** : rédigées, jamais lancées par un agent (`CLAUDE.md` du dépôt). Acerola lance lui-même les déploiements de modèles et le benchmark s'il passe par son identité.
- **Aucun secret** ni donnée personnelle ; aucune URL interne dans le rapport (`Exam/prompt.md` §4.2).
- **Accessibilité** : exigée explicitement pour les synthèses (C6) et la documentation (C8), avec les recommandations Valentin Haüy et AcceDe.
- **Calendrier [Acerola]** : rapport voulu **aujourd'hui, 03/11/2026** ; remise avant le 06/11 ; soutenance le 12/11. Aucune session de veille future ne peut donc servir de preuve dans le rapport.
- **PDF remis [Claude]** : aucun `🔴 À CONFIRMER` dans la version finale. Chaque point non résolu devient un 🟡 ou un ❌ avec une phrase d'écart assumé, comme dans E1 et E3, ou disparaît s'il n'est pas exigé. Un article sans biographie ni date n'est pas présenté comme source qualifiée.
- **Git** : une branche, une PR en brouillon, jamais de push sur `main`.

## 6. Contenu décidé

### 6.1 C6 : veille

**Thème [Acerola, sur proposition de Claude]** : « Industrialiser des agents IA sur Microsoft Foundry : harnais, RAG et gouvernance des identités ». Le référentiel demande un outil « et/ou » une réglementation : un thème centré sur un outil suffit.

**Faits donnés par Acerola**
- Veille puis création ou modification des présentations le dimanche soir, de 20 h à 22 h.
- Agrégation : abonnement Medium, avec articles reçus quotidiennement, et une vingtaine de sources suivies (captures fournies). Le libellé Gmail `Medium` compte 2 309 messages (capture du 03/11). Cela prouve la réception et le rythme des envois, **pas la lecture** : le compteur de 1 464 affiché à côté du libellé semble être celui des non-lus, à ne pas présenter comme des articles lus.
- Tri : listes de lecture privées « Harness engineering » (8), « RAG » (7), « Claude » (5), « Text 2 SQL » (2). Ces 22 articles sont la preuve de lecture et de sélection.
- Destinataire des synthèses : son **formateur**, par dépôt sur le canal Discord **`veille`**. Capture du canal à fournir pour en faire une preuve.
- Formulation validée par Acerola : lecture le dimanche soir, finalisation parfois en semaine.
- Décisions issues de la veille : `~/.claude/CLAUDE.md`, avec Ponytail et Graphify.
- Articles Foundry : [Tim Hanewich sur Entra ID](https://timhanewich.medium.com/how-to-use-microsoft-foundry-via-entra-id-authentication-with-step-by-step-screenshots-f6d381d50f3a) et [Cloud Atlas sur l'identité des agents](https://cloudatlas.me/agent-governance-on-microsoft-foundry-part-i-which-identity-makes-the-call-0a49f3f12e1f).

**Preuves constatées** : `simplon/vieille/`.

| Fichier | Création (Paris) | Sources |
|---|---|---|
| `superpowers_presentation.pptx` | mer. 08/07, 8 h 47 | GitHub officiel, Medium (U. Mittal), builder.io, DataCamp, YouTube |
| `pyramide-des-tests.pptx` | mar. 04/08, 22 h 19 | Aucune dans les diapositives |
| `microservices-agentiques.pptx` | nuit du 13 au 14/09, 0 h 06 | Section 4 du `.md` associé (à lire) |

**Formulation** : une seule date de fichier correspond au créneau du dimanche. Le rapport ne dit donc pas « chaque dimanche ». La récurrence d'une heure par semaine est **déclarée et cohérente avec les traces, mais pas prouvée séance par séance** : critère en 🟡, avec phrase d'écart **[Claude]**.

**Sources qualifiées à partir des captures d'Acerola**

| Article | Auteur | Date | Point de vigilance |
|---|---|---|---|
| How to use Microsoft Foundry via Entra ID Authentication | Tim Hanewich, Solution Engineer chez Microsoft (521 abonnés) | 30/12/2025 | Employé de l'éditeur : à confirmer par Microsoft Learn |
| Agent Governance on Microsoft Foundry, Part I | Ozgur Guler, AI Architect, ex-AWS et ex-Microsoft (628 abonnés) | « il y a 13 heures » à la capture, soit début novembre 2026 | Publié **après** les décisions du projet |

Le critère d'« absence d'intérêts personnels » n'est donc pas pleinement rempli pour le premier auteur : le rapport le dit et s'appuie sur la confirmation par une autre source. L'article de Guler **ne peut pas être présenté comme l'origine** du canal LLM du 22/10 : il le conforte a posteriori. Aucune date de lecture n'est connue pour celui de Hanewich : il est présenté de même.

**Ce qui reste à produire**
- Fiche de fiabilité pour ces sources et pour celles des présentations, sans qualifier ce qui n'est pas renseigné.
- Au moins une ou deux sources sur l'accessibilité et sur la gestion des données **[Claude]**, sourcées et datées (recommandations Valentin Haüy et AcceDe, CNIL).
- Une synthèse dans un format accessible, déposée sur le canal `veille` par Acerola **[Claude, à accepter]**. L'accessibilité des `.pptx` n'a pas été vérifiée : la mention reste 🟡 si la vérification n'a pas lieu.
- Tableau article → décision → effet dans le projet. Un article n'est donné comme origine d'une décision que s'il a été lu avant celle-ci.

### 6.2 C7 : benchmark

**Commanditaire et besoin [Claude, brouillon, Acerola n'a pas relu ce libellé]** : un courtier régional fictif (le référentiel accepte un besoin fictif) veut aider ses gestionnaires à préparer une proposition de contrat auto à partir de la loi et des notices, avec des citations vérifiables, en moins de 20 minutes par dossier et avec validation humaine. Le besoin d'Acerola : « créer des contrats d'assurance auto à partir de notices, articles de lois ». La V1 s'arrête au **brouillon validé** (`brief3/besoins-contrats-auto.md`).

**Motif du choix, à présenter tel quel** : Acerola a retenu Foundry car le centre de formation fournit l'abonnement Azure, et `gpt-4.1-mini` pour ses résumés et son prix. La PR #105 prouve un autre motif : `Kimi-K2.5` prenait environ 14 s par appel et dépassait les délais des agents. Le rapport cite les deux et marque ce qui est prouvé.

**Deux usages à comparer [Claude, d'après le dépôt]** : réponse du RAG (`rag/llm.env` : `Kimi-K2.5`) et agents du cluster (`agentic-cluster/agents.toml` : `gpt-4.1-mini`).

**Candidats mesurés [Acerola : déployés sur `svespuce-971`, capture du portail]** : `gpt-4.1-mini` (2025-04-14, créé le 24/10), `gpt-5-mini` (2025-08-07, créé le 03/11), `Kimi-K2.5` (version 1, créé le 23/09), tous en **Global Standard**. Ressource en `swedencentral` (lecture `az` du 03/11).

**Services non retenus, à lister avec leur raison [Claude, raisons à valider]**

| Service | Raison |
|---|---|
| `Llama 4 Maverick` | Essai réel : le portail affiche « Model deployment failed » sur `svespuce-971`, sans motif visible (capture d'Acerola). Le rapport ne suppose aucune cause |
| API directes Anthropic, Mistral | Hors de l'abonnement fourni |
| Modèle auto-hébergé (GPU) | Coût d'infrastructure hors budget |

**Prix officiels** relevés le 03/11/2026 par l'API Azure Retail Prices, Sweden Central, en USD par million de tokens. Le relevé est versionné sous `eval/preuves/`.

| Modèle | Global (déployé) : entrée / sortie | Data Zone : entrée / sortie |
|---|---|---|
| `gpt-4.1-mini` | 0,40 / 1,60 | 0,44 / 1,76 |
| `gpt-5-mini` | 0,25 / 2,00 | 0,275 / 2,20 |
| `Kimi-K2.5` | **Non trouvé** dans cette API | 0,66 / 3,30 |

Pour `Kimi-K2.5`, le coût du benchmark prend le prix Data Zone comme référence et le rapport le signale. Le coût réel se vérifie sur la facturation Azure.

**Écart à annoncer : localisation du traitement.** En Global Standard, les données d'inférence [peuvent être traitées dans n'importe quelle région Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types) ; seules les données au repos restent dans la géographie choisie. Le mode Data Zone UE limite le traitement à l'EU Data Boundary. Ni `docs/donnees/rgpd.md`, ni `docs/secrets.md`, ni le dossier de conception n'abordent ce point. Le rapport l'annonce, vérifie ce que la vue minimisée envoie réellement au modèle, compare le surcoût de 10 % (écart relevé sur `gpt-4.1-mini` et `gpt-5-mini`) et recommande sans présenter le passage en Data Zone comme fait. Le cas est un courtier fictif et des dossiers synthétiques : le rapport distingue cet environnement d'un usage réel **[Claude]**.

**À signaler dans le benchmark** : Microsoft indique `gpt-4.1-mini` comme déprécié, avec un retrait le 14/04/2027 ([calendrier](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule)). Des fils Microsoft Q&A plus anciens donnent octobre 2026 : vérifier la page au moment de rédiger.

**Mesures [Claude]**, même protocole pour chaque candidat :
- citations exactes (articles attendus de `eval/golden.jsonl`) et format de sortie valide ;
- latence p50 et p95, face aux délais de `agents.toml` (Rédacteur : 8 s) ;
- tokens et coût par dossier, face au seuil de 0,15 $ de l'alerte AL-6 ;
- appels d'outil : `search_rag` fonctionne-t-il avec le modèle ?

**Ce qui est exécuté [Claude]**
- **Usage RAG** : les 3 candidats rejouent le jeu d'évaluation par la chaîne existante (`make eval`, `eval/golden.jsonl`, `eval/questions-demo.jsonl`).
- **Usage agents** : appels isolés par agent, avec les vrais prompts, les réglages de `agents.toml` et un petit jeu fixe de dossiers fictifs du seed. Pas de Saga complète par modèle : 9 jours ne le permettent pas. Le « coût par dossier » est donc la **somme des coûts des quatre agents**, et le rapport nomme cette approximation. L'exigence de moins de 20 minutes par dossier n'est **pas** testée : elle relève de l'ensemble du parcours, pas du seul modèle.
- **Chemin** : tous les appels passent par la gateway (`/api/llm`), comme en production. Foundry n'accepte que son identité et aucun compte humain ne l'appelle en direct.
- **Exécution** : Acerola déploie les candidats manquants et lance les commandes, car ce sont des écritures Azure ou des appels sous son identité.

**Critères fixés avant les mesures [Claude]**, pour ne pas ajuster la frontière après coup :

| Mesure | Répond au besoin si | Nature |
|---|---|---|
| Citations et cas d'évaluation | Taux ≥ 0,8, le seuil de la porte existante (`docs/ci-evals.md`) | Bloquant |
| Sortie structurée et appel de `search_rag` | Fonctionnent | Bloquant |
| Disponibilité | Déployable sur `svespuce-971` | Bloquant |
| Latence | Comparée aux délais de `agents.toml` ; la latence réelle est enregistrée même au-delà du délai | **Indicatif** : ces délais ont été réglés sur `gpt-4.1-mini` (l'Actuaire est passé de 1,5 s à 4 s) et les prendre comme seuil le favoriserait |
| Coût par dossier | ≤ 0,15 $ (AL-6) | Indicatif, approximation ci-dessus |
| Date de retrait | Signalée dans les inconvénients | Indicatif |

**Ensembles fonctionnels [Claude]** : réponse citée du RAG · rédaction structurée par agent · appel d'outil · embeddings (documentaire uniquement, `text-embedding-3-small` n'étant pas remis en cause).

**Deux niveaux de comparaison [Claude]**, car le critère parle de « services » et non de modèles :
1. **Services, comparaison documentaire sans mesure** : Foundry, API OpenAI directe, API Anthropic, API Mistral, Amazon Bedrock, Google Vertex AI. Pour chacun : adéquation par ensemble fonctionnel, prérequis, hébergement européen, prix officiel, éco-responsabilité publiée. Une information introuvable s'écrit « non trouvé ». Ils sont écartés sur des raisons sourcées, abonnement fourni compris.
2. **Modèles, mesurés sur Foundry** : les 3 candidats.

**Limite à annoncer** : le jeu est petit (11 cas joués le 27/10, 2 écartés) et ne permet pas de conclusion statistique.

**Éco-responsabilité** : seulement les informations publiées et sourcées, sinon « non publié pour ce modèle ». Les tokens par dossier servent de repère mesuré, pas d'estimation d'émissions.

**Conclusion attendue par le référentiel** : services qui répondent au besoin avec avantages et inconvénients, séparés clairement de ceux qui n'y répondent pas. Elle s'écrit après les mesures. Le résultat n'est pas présumé, y compris s'il contredit le choix actuel.

### 6.3 C8 : paramétrage

Service : Foundry `svespuce-971`, déjà en place. Le rapport documente l'existant et ne le refait pas.

| Critère | Preuve repérée, à vérifier une à une |
|---|---|
| Accessible, avec authentification | `docs/secrets.md`, `infra/llm.sh`, route `/api/llm` de `gateway/README.md` |
| Configuré, répond au besoin | `disableLocalAuth`, rôle réservé à la gateway, `rag/llm.env`, `agents.toml`, résultats d'évals |
| Monitorage opérationnel | Alerte AL-8 et requête `al-8-foundry-429.kql`, `docs/observabilite-app-insights.md`. **Le critère vise « le monitorage disponible du service » : vérifier ce qui existe côté ressource Foundry** |
| Documentation : accès, installation, test, dépendances, données | `docs/secrets.md`, `docs/ci-evals.md`, `docs/exploitation.md` |
| Format accessible | `make docs-pdf` (`tools/docs_pdf.py`, PDF balisé) |

## 7. Forme du rapport

**[Acerola]** Ton, charte graphique et vulgarisation inspirés de E1 et E3.

- Sources de référence : `Exam/sources-livrables (1).zip` (version la plus récente), avec `E1-rapport.md` et `E3-rapport.md`.
- **Structure [Claude, reprise de E1 et E3]** : page de titre avec bandeau (épreuve, candidat, compétences, soutenance, version du dépôt, sommaire) · contexte raconté par un cas concret · une section par compétence avec un encadré « Preuves » · annexes : preuves par compétence, matrice critère → preuve (✅ 🟡 ❌, avec phrase d'écart pour chaque 🟡), écarts à annoncer · **Glossaire en dernier chapitre**, avec équivalents .NET.
- **Ton** : français clair, pédagogique, analogies .NET, personnages fictifs comme Julie et Paul si utile.
- **Charte** (`Exam/prompt.md` §4.3) : bleu `#1E3A8A` plateforme, gris `#E5E7EB` et bord `#6B7280` composant, vert `#15803D` nominal, rouge `#B91C1C` pointillé risque, violet `#7C3AED` et fond `#EDE9FE` porte qualité ; légende systématique ; `<title>` et `<desc>` dans chaque SVG ; information jamais portée par la seule couleur.
- **Feuille de style** : absente des archives et du graphe Graphify. À reconstituer d'après les PDF E1 et E3, puis à **montrer à Acerola sur une page** avant de rédiger le reste **[Claude]**.
- **Export** : Markdown → HTML → Chrome sans interface, PDF balisé en `lang="fr"`. `tools/docs_pdf.py` donne la mécanique ; pandoc n'est pas installé sur le poste.
- **Vocabulaire** : « Saga » pour l'orchestrateur, jamais « harnais » ni « superviseur LLM ». Le harnais est le code autour de l'appel au LLM (dossier de conception §4.5). « Fabrique » (*Factory*) et non « Fabric », qui évoque Microsoft Fabric. Ne pas écrire que la fabrique « sérialise » les agents : `serialisation.py` traite l'état du dossier.

## 8. Critères du référentiel à couvrir (pp. 6-10)

**C6** : thème lié à un outil ou une réglementation de la mise en situation · temps planifiés, au moins 1 h par semaine · outils d'agrégation cohérents avec les sources et le budget · synthèses communiquées dans un format accessible · informations conformes au thème · sources fiables (critères du §6.1).

**C7** : besoin reformulé avec objectifs et contraintes · services étudiés et non étudiés · raisons d'écarter · adéquation par ensemble fonctionnel · démarche éco-responsable · contraintes techniques et prérequis · conclusions délimitant clairement ce qui répond ou non au besoin.

**C8** : service accessible, avec authentification · configuré correctement · monitorage opérationnel · documentation (accès, installation, test, dépendances, interconnexions, données) · communiquée dans un format accessible.

## 9. Laissé au constructeur

- Où placer le script de benchmark et sa forme, en réutilisant `make eval` et `eval/` s'ils conviennent. Prix et sorties versionnés sous `eval/preuves/`.
- Plan détaillé du rapport et pagination, dans les 15 à 20 pages.
- Schémas : réutiliser ceux du dossier de conception quand ils conviennent, sinon SVG à la charte.
- Lieu des sources du rapport : à côté de E1 et E3 dans `Exam/`, hors du dépôt Git, sauf meilleure raison **[Claude]**.

## 10. Questions ouvertes pour Acerola

- Validation du libellé du besoin et des raisons d'écarter.
- Capture du canal Discord `veille`.
- Lancement des commandes du benchmark, sous son identité.
