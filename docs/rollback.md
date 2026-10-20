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
2. Il crée une nouvelle révision depuis `infra/containerapp.yaml` avec les **deux images à ce SHA**
   (`agentinsurflow-gateway`, `agentinsurflow-rag`) ; l'image PostgreSQL annexe (`agentinsurflow-postgres:1`), les
   variables et les secrets des Container Apps restent identiques.
3. Le **test de fumée**, par la gateway, vérifie que `/health` et `/health/rag` renvoient ce SHA et que
   `/api/reponses` répond 401 sans jeton.
4. Le run reste dans le journal Actions : c'est la trace du rollback.

Aucune reconstruction : les images sont **immuables** (tag = SHA) et déjà dans l'ACR. Le prompt et la version
du LLM (`llm.env`) étant **dans l'image**, le rollback les restaure aussi.

⚠️ **Base annexe éphémère** : la nouvelle révision repart d'une base vide (migrations au démarrage). Après un
rollback, le corpus est à réingérer (`make ingest URL=<environnement> INSTANTANE=data/raw/…`) avant que l'agent
réponde à nouveau avec des citations.

> 🔁 **Analogie .NET** : c'est un *swap* de slot App Service, sauf qu'on repointe une image existante au lieu
> d'échanger deux slots.

⚠️ La « version précédente » est l'avant-dernière révision **créée**. Relancer `make rollback` revient donc à la
version qu'on vient de quitter, ce qui sert à revenir en avant. Pour une version précise : `make rollback TAG=<sha>`.

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
