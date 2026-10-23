# Rollback en une seule opération

**Critère 4 de la grille** : « Le retour à la version précédente est montré, en une opération »
(source : grille-atelier-2-socle-chaine.pdf). La procédure suit le dossier : « Code d'un service → redéployer
l'image précédente, < 5 min » (source : dossier-conception-v1.md, §7.3).

## L'opération

```bash
make rollback                 # = gh workflow run deploy.yml -f environnement=production -f tag=
```

On peut aussi passer par l'interface : Actions › **deploy** › *Run workflow* › `production`, tag vide.

## Ce qui se passe

1. `deploy.yml` lit les révisions de la Container App et retient le **SHA de l'avant-dernière révision**, lu sur
   l'image de son conteneur `gateway`.
2. Il crée une nouvelle révision depuis `infra/containerapp.yaml` avec les **images à ce SHA**
   (`agentinsurflow-gateway` pour la principale, `agentinsurflow-underwriting` pour celle d'underwriting-admin, déployée avant, `agentinsurflow-mcp` pour la Container App du serveur MCP, `agentinsurflow-cluster` pour celle du cluster d'agents, déployée après le MCP et avant la gateway, `agentinsurflow-rag` pour celle de rag, déployée en dernier) ; l'image PostgreSQL annexe (`agentinsurflow-postgres:2`), les
   variables et les secrets des Container Apps restent identiques.
3. Le **test de fumée**, par la gateway, vérifie que `/health`, `/health/rag`, `/health/underwriting`, `/health/mcp` et `/health/calcul` renvoient ce SHA et que
   `/api/reponses`, `/api/calcul/evaluer` et `/api/llm/v1/chat/completions` répondent 401 sans jeton.
4. Le run reste dans le journal Actions : c'est la trace du rollback.

Aucune reconstruction : les images sont **immuables** (tag = SHA) et déjà dans l'ACR. Le prompt et la version
du LLM (`llm.env`) étant **dans l'image**, le rollback les restaure aussi.

⚠️ **Base annexe éphémère** : la nouvelle révision repart d'une base vide (migrations au démarrage). Après la fumée,
`deploy.yml` réingère le dernier instantané versionné (`data/raw/`) du commit qui lance le workflow : pour un
rollback lancé à la main, celui de `main`, pas celui du SHA restauré.

> 🔁 **Analogie .NET** : c'est un *swap* de slot App Service, sauf qu'on repointe une image existante au lieu
> d'échanger deux slots.

⚠️ La « version précédente » est l'avant-dernière révision **créée**. Relancer `make rollback` revient donc à la
version qu'on vient de quitter, ce qui sert à revenir en avant. Pour une version précise : `make rollback TAG=<sha>`.

Le rollback est la **seule** façon de servir une release inférieure : la chaîne, elle, refuse avant la production
toute release sous celle en service (`tools/version.py --verifier`).

## Scénario de répétition

| # | Geste | Vérification |
|---|---|---|
| 1 | Noter la version servie | `curl -s https://<prod>/health` (et `/health/rag`) → `version = A` |
| 2 | Merger une PR visible, par exemple un changement d'exemple dans un schéma de l'API (Swagger) | La chaîne passe ; `/health` → `version = B` |
| 3 | `make rollback` (**démarrer le chrono**) | Run `deploy` vert ; `/health` → `version = A` (**arrêter le chrono**) |
| 4 | `make rollback TAG=B` | `/health` → `version = B` : retour en avant |

Durée mesurée : `🔴 À MESURER` à la répétition. Ne pas annoncer de chiffre avant de l'avoir mesuré.

## Preuves à versionner

| Preuve | Commande | Fichier |
|---|---|---|
| Journal du run de rollback | `make preuve RUN=<id> NOM=rollback-AAAA-MM-JJ` | `eval/preuves/rollback-AAAA-MM-JJ.log` |
| Versions avant / après | `curl -s …/health` avant et après, collés dans le fichier | `eval/preuves/rollback-AAAA-MM-JJ.md` |
| Capture du run | capture d'écran | `eval/preuves/rollback-AAAA-MM-JJ.png` |

## Le cluster d'agents

`agentinsurflow-cluster:<SHA>` (≈ 9 Go) est une cinquième image au même SHA, dans sa Container App (entrée interne, une réplique). Ordre : base annexe, underwriting-admin, MCP, cluster, gateway, rag. Un rollback vers un SHA antérieur à son introduction est **refusé** (l'image n'existe pas). La base annexe repart vide : les points de reprise du graphe (`agent_state`) sont perdus, un dossier en attente de revue doit être réévalué. Pendant un déploiement, deux révisions du cluster peuvent coexister brièvement (R17). Fumée : `/health/cluster`.

## Limite : les quatre images du SHA

La base annexe, underwriting-admin, le serveur MCP et rag ont chacun leur Container App : `deploy.yml` redéploie la base annexe d'abord, puis underwriting-admin (la gateway en lit le FQDN interne), le MCP, la principale (gateway) et enfin rag, tous au même SHA (la base n'a pas d'image au SHA : image fixe `agentinsurflow-postgres:2` (le tag passe à `:2` avec le schéma `agent_state` du cluster), mais une nouvelle révision à chaque déploiement, car `DEPLOIEMENT` = SHA). Ordre voulu : la base est éphémère et repart vide à chaque déploiement, comme avant la séparation ; underwriting-admin et rag attendent PostgreSQL et y jouent leurs migrations à leur démarrage, donc ils viennent après. Entre la nouvelle base et le redémarrage de ses clients, les anciennes révisions de la principale et de rag n'ont plus de données : brève indisponibilité attendue (le corpus est réingéré en fin de déploiement). Si une étape échoue en cours de route, il n'y a pas de retour automatique : les apps sont alors à des SHA différents ; relancer le déploiement, ou `make rollback`. Un rollback vers une révision antérieure à ces séparations exige que `UW_APP_NAME`, `MCP_APP_NAME`, `RAG_APP_NAME` et `PG_APP_NAME` existent (`make infra`). Un rollback vers une révision **antérieure à #70** (rag encore dans la principale) laisse la gateway sans cluster `llm` et rag sur son ancien câblage : à éviter, redéployer plutôt une version ≥ #70.

Un déploiement ou un rollback pose les **quatre** images (`rag`, `underwriting`, `gateway`, `agentinsurflow-mcp`) au même SHA, lu sur la gateway de la révision visée. `deploy.yml` vérifie dans l'ACR (lecture seule) qu'elles existent toutes avant de toucher à l'application, sinon il échoue sans rien déployer. Conséquence : un rollback vers une révision **antérieure à U5** est refusé (`agentinsurflow-underwriting:<ancien SHA>` n'a jamais été construite). De même, un rollback vers un SHA **antérieur à `feat/mcp`** est refusé : aucune image `agentinsurflow-mcp:<SHA>` n'existe. Le premier rollback possible est vers la première révision à 4 images (fail-closed : un rollback vers un SHA antérieur à la séparation du MCP n'est **pas pris en charge**) ; au-delà, redéployer à la main un SHA précis (`make rollback TAG=<sha>`).

Un rollback vers un commit antérieur à `fonction-calcul/` (avant T9) échoue au déploiement de la Function : fail-closed, redéployer une version ≥ T9.
