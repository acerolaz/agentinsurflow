# Paramétrage par agent du cluster : modèle, température, prompt, budget de tokens, délai

*24/10/2026. Demande d'Acerola, après l'E2E de staging : Kimi-K2.5 (≈ 14 s par appel) faisait tomber chaque agent en `llm_ko`, et #105 a dû donner au cluster un modèle unique (`agentic-cluster/llm.env`).*

## 1. Intention

Acerola calibre lui-même chaque **sous-agent** du cluster (Pièces, Analyste, Rédacteur, Actuaire) en coût, qualité et latence, sans toucher au code : un fichier versionné, modifié par PR. Ce réglage est aussi une **preuve pour l'évaluateur** : chaque agent a son modèle et son budget, et chaque décision trace le réglage qui l'a produite.

La **Saga** n'est pas concernée : automate déterministe, sans LLM (#106, #107).

## 2. Ce qui est décidé (Acerola)

| Sujet | Décision |
|---|---|
| Emplacement | Un **fichier versionné** dans le dépôt, modifié par PR, lu au démarrage du cluster |
| « Rôle » | Le **prompt système** de l'agent |
| Budget de tokens | **Par appel** au modèle (`max_tokens` de la réponse) |
| Dépassement | Repli de l'agent ⇒ revue humaine, comme une panne du LLM, avec une **cause distincte** |
| Délai par agent | **Paramétrable** aussi (aujourd'hui en dur : `SpecAgent.delai_s`) |
| Validation | **Oui** : modèles réellement déployés, température bornée, refus d'une configuration invalide |
| Qui, pourquoi | Acerola, pour calibrer ; **avec preuve** à montrer |

## 3. Le fichier `agentic-cluster/agents.toml`

Une section par sous-agent, les quatre obligatoires, aucune autre clé :

```toml
# Réglage des sous-agents du cluster (la Saga n'a pas de LLM). Modifié par PR ; lu au démarrage.
[pieces]
modele = "gpt-4.1-mini"      # nom du déploiement Foundry
temperature = 0.0            # [0, 1]
max_tokens = 400             # par appel, réponse seule
delai_s = 1.5                # garde de l'agent (référence + LLM)
prompt = "pieces.md"         # prompt système, dans infrastructure/llm/prompts/

[analyste]
modele = "gpt-4.1-mini"
temperature = 0.0
max_tokens = 400
delai_s = 2.0
prompt = "analyste.md"

[redacteur]
modele = "gpt-4.1-mini"
temperature = 0.2
max_tokens = 1200
delai_s = 8.0
prompt = "redacteur.md"

[actuaire]
modele = "gpt-4.1-mini"
temperature = 0.0
max_tokens = 400
delai_s = 1.5
prompt = "actuaire.md"
```

- **Valeurs initiales : mon choix**, à calibrer par Acerola. Délais = valeurs actuelles de `domain/specs.py` ; modèle = celui de #105 ; température 0 (proposition reproductible), 0,2 pour le Rédacteur (texte de la fiche) ; `max_tokens` dimensionnés large pour une note ou une fiche structurée.
- **Les prompts restent dans leurs fichiers `.md`** (mon choix) : relisibles, et `version_prompt` (empreinte SHA-256 du fichier) ne change pas de calcul.
- **Format TOML** (mon choix) : lu par `tomllib` (stdlib), commentaires possibles, aucune dépendance.
- Il **remplace `agentic-cluster/llm.env`** (#105) : `AZURE_OPENAI_DEPLOYMENT` disparaît de la configuration du cluster (`deploy.yml`, `infra/containerapp-cluster.yaml`, `docker-compose.yml`, `.env.example`). rag garde `rag/llm.env`.
- `tours_max` et les outils MCP restent dans `domain/specs.py` : ce sont des bornes du dossier (§ 4.9), pas des réglages de calibrage.

## 4. Validation

**Au démarrage du cluster** (le cluster ne démarre pas, la sonde échoue, le déploiement et sa fumée échouent) si :
- une des quatre sections manque, ou une section ou une clé inconnue apparaît ;
- `temperature` ∉ [0, 1], `max_tokens` ≤ 0 ou > 16 000 (mon choix de plafond), `delai_s` ≤ 0 ;
- **la somme des `delai_s` dépasse la garde globale** (`INSURFLOW_BUDGET_S`, 25 s par défaut) : sinon K5 (< 30 s) ne tient plus ;
- le fichier de prompt n'existe pas.

Le message d'erreur nomme l'agent et la clé. Ces règles sont **pures** (domaine, testées en TU) ; la lecture du fichier est un adapter.

**Au déploiement** (`deploy.yml`, avant toute mise à jour de Container App) : chaque `modele` cité doit exister comme déploiement de la ressource Foundry ; sinon le déploiement est refusé avec le nom manquant. C'est le seul endroit qui a le droit de lister Foundry (identité de CI, `Contributor` sur `svespuceRG`) ; le cluster ne l'a pas. Le nom de la ressource se déduit de `vars.FOUNDRY_ENDPOINT` (`https://<nom>.openai.azure.com`).

- Le fichier vérifié est **celui du SHA déployé** (même commit que l'image : un rollback vérifie l'ancien réglage), pas celui de `main`.
- Le fichier est **dans l'image** : `agentic-cluster/Dockerfile` le copie comme `garde_fous.env`. Le cluster lit sa copie, jamais une variable d'environnement.

## 5. Comportement

- `modele_chat(agent, …)` construit `ChatOpenAI` avec le `modele`, la `temperature` et le `max_tokens` de l'agent (toujours par la gateway, `/api/llm/v1/`).
- La garde de l'agent (`executer_agent`, `pas`) lit `delai_s` dans le réglage au lieu de `SPECS[nom].delai_s`.
- **Réponse coupée par `max_tokens`** (fin de génération « longueur ») ⇒ repli de l'agent, cause **`budget_tokens`** (et non `llm_ko`) ; le dossier part en revue humaine avec le message neutre habituel. Le mécanisme de détection est laissé au builder (exception de longueur d'`openai`, ou `finish_reason == "length"` de la dernière réponse) ; un test doit le prouver.
- Une autre panne du LLM reste `llm_ko` ; `garde_fou:pii` reste distinct (K5).

## 6. Preuve (ce que l'évaluateur voit)

- **`audit.agent`** (journal JSON) et le **span `invoke_agent`** portent, en plus de `version_prompt` : le modèle, la température, `max_tokens`, et les **tokens consommés** (entrée, sortie, somme des appels de l'agent ; 0 en repli sans appel). Attributs du span selon les conventions OTel GenAI : `gen_ai.request.model`, `gen_ai.request.temperature`, `gen_ai.request.max_tokens`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`.
- **`GET /health`** du cluster (déjà lu par `/health/cluster` et la fumée) expose, à côté des empreintes de prompt, le réglage de chaque agent (`modele`, `temperature`, `max_tokens`, `delai_s`) : aucun secret, ce sont des valeurs du dépôt.
- `docs/contrat-personnel.md` : une ligne de preuve (fichier, validation, trace) ; `agentic-cluster/README.md` : le fichier et comment le modifier.

## 7. Non-objectifs

- Changer un réglage **sans redéployer** (variable GitHub, base, console).
- Paramétrer la Saga, `tours_max` ou les outils MCP.
- Restreindre à la gateway quel appelant utilise quel modèle (voir la vérification du 24/10 : seuls rag et les quatre sous-agents détiennent le rôle `LLM`).
- Budget de tokens **cumulé** par évaluation ou par appelant (#72).

## 8. Anti-objectifs (échec même si « ça marche »)

- Un réglage invalide qui démarre quand même et se découvre en production.
- Un modèle absent de Foundry qui passe le déploiement et finit en `llm_ko` silencieux.
- Une décision dont on ne peut pas dire, après coup, avec quel modèle et quel prompt elle a été rédigée.
- Le texte des prompts ou des observations dans l'audit (seules les empreintes y vont).

## 9. Contraintes

- Architecture hexagonale : le réglage est un value object du **domaine** (règles de validation pures, TU) ; la lecture TOML est dans `infrastructure/` ; `application/` reçoit le réglage par `Dependances`, jamais par import d'un adapter. Le test d'architecture existant le vérifie.
- TDD ; `make lint`, `make test`, `make test-integration` verts ; couverture ≥ 80 %.
- Aucune écriture Azure par un agent : la vérification Foundry de `deploy.yml` est en **lecture seule**.
- Versions de dépendances inchangées (`tomllib` est dans la stdlib).

## 10. Laissé au builder

- Détection de la troncature (§ 5) et lecture de l'usage des tokens dans la réponse LangChain.
- Découpage exact du value object et de son chargeur ; nom de la variable qui pointe vers le fichier si un test en a besoin (par défaut : le fichier du paquet).
- Mise à jour des tests existants qui lisent `SPECS[nom].delai_s` ou `AZURE_OPENAI_DEPLOYMENT`.
