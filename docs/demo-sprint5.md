# Démo — sprint 5, « les 10 minutes » : parcours, livraison automatique, alerte

*Spec : [`superpowers/specs/2026-10-28-o6-demo-10-min-design.md`](superpowers/specs/2026-10-28-o6-demo-10-min-design.md) (§ 8 bis prime sur le § 4). Issue #157. Compétence visée : C6, avec C11, C20 et C21 en appui. On montre du réel, jamais une capture, sauf en plan B.*

*Durée totale du tableau : **10:00** (1:00 + 3:00 + 1:30 + 1:30 + 1:30 + 1:00 + 0:30). Les durées de chaque séquence sont des budgets : à confirmer par la répétition.*

## Inconnues

- Date de la démo (atelier n° 5) : `🔴 À CONFIRMER`.
- Gestionnaire de la démo (A) et seed `SEED_GESTIONNAIRE_A` qui en découle : `🔴 À CONFIRMER`. Le formateur était A pour la démo du 30/10. Les dossiers `AIF-2026-000001` à `000003` appartiennent à A ; ne pas toucher à `000007` à `000009` (CI).
- Durée réelle de chaque séquence : `🔴 À CONFIRMER` par les deux répétitions ([gabarit](../eval/preuves/repetition-demo-sprint5-AAAA-MM-JJ.md)).
- Nom des onglets App Insights et du tableau de bord de production : `vigie-production` et `vigie-staging` sont les noms créés par `infra/vigie.sh` (ligne 129). Leur existence dans le portail est `🔴 À CONFIRMER` (S2 est sur `main`, l'installation en production dépend de l'exécution à la main de `infra/vigie.sh`).

## Avant (T − 65 min → T − 0)

Pourquoi si tôt : une fusion lance `ci-cd.yml`, qui redéploie et ressème le staging puis la production. Le run doit **attendre l'approbation de la production** avant que `llm-off` soit lancé (une fusion remettrait sinon `INSURFLOW_LLM_ACTIF=true`, et les contrôles de staging échoueraient avec `llm-off` actif). L'approbation passe par l'environnement `production` (`environment:` de `.github/workflows/deploy.yml`, ligne 46 ; GitHub : revue obligatoire, `required_reviewers`).

### Durées mesurées

| Mesure | Valeur | Source |
|---|---|---|
| Push → job `release` terminé (le run attend alors l'approbation), run lent | **48:04** (17:16:04Z → 18:04:08Z) dont `staging / deploy` 32:47 et `build` 5:20 | run `40734064386` du 28/10 |
| Même mesure, run rapide | 16:51 (00:12:31Z → 00:29:22Z) dont `staging / deploy` 7:00 | run `40607269651` du 28/10 |
| `e2e-staging` | 1:16 (run lent), 1:15 (run rapide) | runs `40734064386`, `40607269651` |
| `evals` | **sautés** (`skipped`) dans ces deux runs : une PR de doc ne touche pas `DECLENCHEURS_EVALS` (`.github/workflows/ci-cd.yml`, ligne 25) | runs `40734064386`, `40607269651` |
| Fin de `release` → début de `production / deploy` | 2:55 : l'attente de l'approbation (cliquée par un humain) | run `40734064386` |
| `production / deploy` | 17:43 (18:07:03Z → 18:24:46Z) | run `40734064386` |
| Run de la release #171 | build de 13:38 (21:17:35Z → 21:31:13Z) ; `staging / deploy` démarré à 21:31:32Z, encore en cours à 21:36Z, sans durée finale | run `40770295428` |

La tendance est à la hausse : le déploiement du staging compte maintenant sept étapes de 5 min environ (Function, base, underwriting, MCP, cluster, gateway, rag). Il faut donc retenir **le cas lent, 48 min**.

**Heure de fusion conseillée : T − 65 min.** Au pire mesuré (48 min), le run attend l'approbation à T − 17 min, avant la limite de T − 15 min. Si le run #171 se termine plus lentement, corriger cette heure (elle est à confirmer par la répétition).

### Chronologie

| Quand | Action | Vérification |
|---|---|---|
| **T − 65** | Fusionner la PR de démo (une vraie petite PR utile, sans risque : une PR de doc). `ci-cd.yml` démarre | Run visible : `gh run list --workflow ci-cd.yml --branch main --limit 1` |
| **T − 65 → T − 17** | Attendre. Surveiller le run. **Ne pas lancer `llm-off` avant la fin de `e2e-staging` et, si les evals tournent, avant la fin de `evals`** | Job `release` vert, run « en attente d'approbation » (production) |
| **T − 30** | Liste de préparation ci-dessous (sauf `llm-off`) | — |
| **T − 17 → T − 15** | Dès que le run attend l'approbation (au plus tard T − 15) : `make recette ACTION=llm-off` (staging). Le script attend la nouvelle révision et affiche « prête, 100 % du trafic » (jusqu'à 5 min) | `infra/recette.sh`, lignes 4 à 6 et 36 à 39 |
| **≈ T − 10** | Dès que le script affiche la révision prête, une évaluation dans l'espace gestionnaire de **staging** (`https://insurflow-staging.redstone-0f3be5e1.swedencentral.azurecontainerapps.io/app/`) : elle part en `REVUE_HUMAINE`, message « Service temporairement indisponible », cause `llm_ko` | Doc : `docs/exploitation.md`, ligne 192 (« La panne type : le LLM coupé (alerte AL-2) ») |
| **T − 10 → T − 0** | Attendre l'e-mail AL-2 : règle évaluée toutes les 5 min sur une fenêtre de 5 min, seuil au moins 1 erreur `llm_ko` (`infra/vigie/alertes.tsv`) ; on compte 5 à 10 min | Boîte mail |

L'approbation n'est **pas** cliquée avant la démo : elle l'est en direct à 8:30. Les dossiers montrés viennent du déploiement de la veille au soir ; le déploiement de production, qui ressème la base, a lieu après le parcours.

### Liste de préparation (T − 30)

- [ ] La PR de démo est fusionnée et le run `ci-cd.yml` attend l'approbation de la production (lien du run noté).
- [ ] Le gestionnaire de démo est connecté sur la production : `https://aibrokerflow.fr/app/` (`PROD_URL`, `README.md` ligne 321), carte « Gestionnaire A » `🔴 À CONFIRMER`.
- [ ] Le compte a reçu les droits de relecture sur l'App Insights de production et de staging, et la fiche AL-2 est ouverte.
- [ ] Deux dossiers frais de A, prêts : un pour le parcours de bout en bout (`AIF-2026-00000N`, `🔴 À CONFIRMER` après le déploiement de la veille), un de réserve. La Function de calcul est réveillée (premier appel avant la démo : un démarrage à froid a coûté 10 s dans la recette du 27/10).
- [ ] La boîte mail destinataire de l'alerte (`ALERTE_EMAIL`) est ouverte.
- [ ] Un export ou une capture de l'e-mail AL-2 d'une répétition, en plan B.
- [ ] Le terminal est à la racine du dépôt, `az login` fait.

### Onglets à ouvrir (dans cet ordre)

1. Espace gestionnaire de **production** : `https://aibrokerflow.fr/app/`.
2. Application Insights `appi-insurflow-production` : Transaction Diagnostics, Application Map, Live Metrics (`docs/exploitation.md`, lignes 159 à 171).
3. Tableau de bord `vigie-production`, puis `vigie-staging` (portail Azure, créés par `infra/vigie.sh`).
4. Boîte mail (alerte AL-2).
5. Run GitHub `ci-cd.yml` de la fusion de démo, et `Settings › Environments › production` pour l'approbation.
6. Fiche **AL-2** de `docs/exploitation.md` (section 6, ligne 243).
7. Espace gestionnaire de **staging** (la panne y est lue).

## Tableau minuté

| Temps | Action à l'écran | Phrase à dire (rattachée à une preuve) | Plan B |
|---|---|---|---|
| **0:00 → 1:00** (1:00) | Le schéma mermaid de la tête du `README.md`, en une phrase : gateway seule exposée, agents, serveur MCP, calcul, rag | « Un dossier d'assurance auto est instruit par un cluster d'agents ; un humain valide. Voilà ce que je vais montrer : le parcours, une alerte et une livraison. » | Le schéma mermaid du `README.md` (ligne 10), déjà ouvert dans un onglet |
| **1:00 → 4:00** (3:00) | Production, espace gestionnaire (`/app/`) : connexion A, dossier frais, **évaluation** (jusqu'à 14,9 s au p95, `eval/preuves/evals-2026-10-27.json` ; la frise avance), détail d'une étape avec son `trace_id`, **revue humaine** avec motif, contrat | « La décision vient du barème, pas du modèle : l'agent propose, le gestionnaire valide, et la trace de chaque étape est conservée. » | Production indisponible : même parcours en staging (autre dossier), puis `make up` en local. Évaluation lente : passer au dossier de réserve ; le détail d'étape et le contrat d'un dossier déjà évalué restent montrables |
| **4:00 → 5:30** (1:30) | App Insights de production : **Transaction Diagnostics** sur la même évaluation (recherche par `trace_id`), **Application Map**, **Live Metrics** | « La même évaluation, vue de l'intérieur : de la gateway au serveur MCP, avec les durées de chaque appel. » | La trace de la recette du 27/10 : `eval/preuves/recette-k-2026-10-27-staging.md` (trace `1f5f46fa564ac39f07f76536e0794659`) ; ou `GET /api/traces/{trace_id}` |
| **5:30 → 7:00** (1:30) | Tableau de bord `vigie-production` : tuile « Comment lire ce tableau », puis « Alertes en cours » et les tuiles hors objectif | « Ce tableau répond à une question par tuile, même sans être développeur : tout est dans ses objectifs. » | Tableau de staging ; sinon section 4 de `docs/exploitation.md` (ligne 142) lue à voix haute |
| **7:00 → 8:30** (1:30) | **L'alerte** : e-mail **AL-2** reçu, tableau de bord `vigie-staging` (« Alertes en cours »), fiche AL-2 de `docs/exploitation.md` (ligne 243), puis l'action `make recette ACTION=llm-on` (montrée, lancée à la clôture) | « Le LLM a été coupé exprès en staging ; l'alerte part, la fiche donne la cause (`llm_ko`) et la commande pour rétablir. » | E-mail non arrivé : l'alerte « déclenchée » dans Azure Monitor (portail), et l'e-mail d'une répétition. Aucune alerte : lancer la requête `infra/vigie/kql/al-2-llm-ko.kql` comme décrit dans la section 5 |
| **8:30 → 9:30** (1:00) | **La livraison** : le run de la fusion, ses jobs verts, puis **clic en direct sur l'approbation** de la production (GitHub, environnement `production`), le job `production / deploy` démarre | « Rien n'a été fait à la main : la fusion a lancé le pipeline, qui a déployé le staging, passé les contrôles et attend maintenant mon accord pour la production. » | Run en échec : montrer la porte qui a bloqué (c'est aussi du réel). Pas de bouton d'approbation : le run de la répétition |
| **9:30 → 10:00** (0:30) | Écran de clôture : le schéma ou le tableau de bord | « Ce qui reste : les suites du sprint 5, et ce que j'ai appris. » | — |

**Total : 1:00 + 3:00 + 1:30 + 1:30 + 1:30 + 1:00 + 0:30 = 10:00.** Aucune marge : si une séquence déborde, couper la fin du parcours (revue et contrat) plutôt que l'alerte ou la livraison.

## Clôture

La production se redéploie après l'approbation (environ 18 min mesurées, run `40734064386`) : ne pas attendre sa fin à l'écran.

1. **Rétablir le LLM du staging** : `make recette ACTION=llm-on`. Le script affiche « prête, 100 % du trafic ».
2. **Vérifier que le staging est revenu à la normale** : lancer une nouvelle évaluation dans l'espace de staging (elle passe avec le LLM actif), puis, une fois la fenêtre de 5 minutes écoulée, relancer `infra/vigie/kql/al-2-llm-ko.kql` : la colonne `valeur` retombe à 0 (`docs/exploitation.md`, lignes 211 à 215).
3. Vérifier le job `production / deploy` jusqu'au bout, puis `GET /health` sur `https://aibrokerflow.fr`.
4. Noter les durées réelles dans le gabarit de répétition.

Une fusion ou un déploiement de staging remet aussi `INSURFLOW_LLM_ACTIF=true` (`infra/recette.sh`, ligne 6) : ne jamais lancer `llm-off` avant que le run n'attende l'approbation.
