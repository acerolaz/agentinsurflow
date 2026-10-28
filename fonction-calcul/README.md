# fonction-calcul

Azure Function (Python 3.12, modèle v2) qui calcule, de façon déterministe, le risque d'un dossier
(barème `evaluer`) et sa prime (formule `calculer`). Aucun LLM, aucune base : les mêmes faits
donnent toujours le même résultat. La protection est Easy Auth (niveau `ANONYMOUS` côté Function) : **seule la gateway** l'appelle (`/api/calcul/*`, rôle `Calcul`, jeton échangé contre celui de son identité managée) ; le serveur MCP passe par elle.

Architecture hexagonale : `agentinsurflow_calcul/domain/` (stdlib seule) porte le barème et la
formule ; `function_app.py` n'est que l'adaptateur HTTP.

**D'où ça vient, qui l'appelle** : cette Function **implémente le barème déterministe de D28** (le LLM ne calcule
jamais le score) et la prime de D65, sous la forme décidée par **D70** : barème et formule versionnés dans le code,
changer = redéployer. Le barème suit la matrice d'évaluation déterministe (règles **R01 → R06**, D50 amendée) et
non plus un fichier `bareme-v1.yaml`. Elle est appelée par les outils **`evaluer_risque`** et **`calculer_prime`** du
[serveur MCP](../serveur-mcp/README.md) (adaptateur `CalculateurPort`, `infrastructure/fonction_calcul/client.py`),
par la gateway (`/api/calcul/evaluer`, `/api/calcul/calculer`) : `evaluer_risque` → gateway → `function_app._risque()`
→ `domain.bareme.evaluer()`. Conception : `docs/superpowers/specs/2026-10-22-calcul-risque-prime-design.md`.

## Barème de risque — `bareme-2026.10-v1`

Toutes les règles sont évaluées ; une seule suffit à refuser, le score est le nombre de règles
déclenchées. Les 36 mois se comptent avant la **date d'effet du contrat** (jamais la date du jour).

| Règle | Condition de refus |
|---|---|
| R01_SUSPENSION | `suspensions >= 1` |
| R02_RESILIATIONS | `resiliations >= 2` |
| R03_CRM | `crm > 1,25` |
| R04_SINISTRES_RESPONSABLES | `nb_sinistres_responsables_trois_ans > 2` |
| R05_SINISTRES_TOTAL | `nb_sinistres_trois_ans > 4` |
| R06_JEUNE_PERMIS_PUISSANCE | `anciennete_permis_mois < 36` et `puissance_fiscale_cv > 7` |

## Formule de prime — `formule-2026.10-v1`

`prime_ht = prime_base × k_permis × k_zone × k_vehicule × k_usage × crm`, puis
`prime_ttc = prime_ht × (1 + taux_taxe)`. `Decimal` partout, arrondi `ROUND_HALF_UP` au centime à la
fin seulement ; mensualité = `prime_ttc / 12` arrondie.

**Le taux de taxe de 18 % est fictif** (démonstration, pas un taux réglementaire).

| Grille | Valeurs |
|---|---|
| `prime_base` | `tiers` 250 · `tiers_etendu` 400 · `tous_risques` 650 |
| `k_permis` (mois) | < 12 : 2,00 · < 24 : 1,50 · < 36 : 1,25 · sinon 1,00 |
| `k_zone` (département) | 75, 92, 93, 94, 13 : 1,25 · 15, 48, 23 : 0,90 · autres : 1,00 |
| `k_vehicule` (CV) | ≤ 4 : 0,90 · ≤ 7 : 1,00 · ≤ 10 : 1,30 · sinon 1,60 |
| `k_usage` | `prive` 0,95 · `prive_trajet` 1,00 · `professionnel` 1,35 |

Aucun coefficient par défaut : une donnée absente (`null`) ou hors grille est refusée (422).

## Contrat HTTP

- `POST /api/evaluer` : les 7 clés de `FaitsRisque` ; entiers JSON (pas de booléen) ou `null`,
  `crm` en chaîne décimale ou `null`. Réponse : `version_bareme`, `classe`, `decision`, `score`,
  `regles` (`regle_id`, `motif`).
- `POST /api/calculer` : les 6 clés de `FaitsPrime` (`formule`, `departement`, `type_usage`, `crm`
  en chaînes ; `anciennete_permis_mois`, `puissance_fiscale_cv` entiers ; ou `null`). Réponse :
  `version_formule`, `prime_ht`, `montant_taxes`, `prime_ttc_annuelle`, `prime_mensuelle`,
  `coefficients` ; montants et coefficients en chaînes.
- `POST /api/frequence` : `crm` (chaîne décimale), `puissance_fiscale_cv` (entier), `departement`
  (chaîne), chacun pouvant valoir `null`. Réponse : `version_modele`, `frequence_annuelle`,
  `variables` (`BonusMalus`, `VehPower`, `Region`). **Comparaison seulement** : la fréquence du GLM
  Poisson (`modeles/`) n'entre ni dans la décision, ni dans la prime, ni dans le rapport. Par la
  gateway : `POST /api/calcul/frequence`, politique `calcul-mcp` (jeton du MCP). `crm` et puissance
  hors des bornes d'entraînement sont bornés (jamais extrapolés) ; un champ `null` ou un DOM
  (971-976, sans région freMTPL2) renvoie 422. Le journal ne porte que
  `glm.frequence version=<v> frequence=<f>`, aucune donnée du profil.
- `GET /api/sante` : `{"version": $APP_VERSION ou "dev", "bareme": …, "formule": …, "modele_frequence": …}`.

Erreurs :

| Statut | Corps | Cas |
|---|---|---|
| 400 | `{"code": "REQUETE_INVALIDE"}` | corps non JSON ou pas un objet, clé manquante ou en trop, mauvais type, `crm` non décimal |
| 422 | `{"code": "DONNEE_HORS_BAREME", "champ": "<nom>"}` | donnée `null` ou hors grille ; seul le nom du champ est renvoyé |
| 422 | `{"code": "DONNEE_HORS_MODELE", "champ": "<nom>"}` | `/api/frequence` : champ `null` ou département sans région (DOM) |

Jamais de log du corps de la requête ni de la réponse (faits du dossier, montants).

## Versionnement

Un changement de règle ou de grille = une nouvelle constante `VERSION_BAREME` / `VERSION_FORMULE`,
un commit, puis un redéploiement. Les versions sont servies par `/api/sante`.

## Exécution locale

```bash
uv run pytest fonction-calcul/tests/unit --no-cov -q     # tests
docker compose build calcul && docker compose up -d calcul   # image locale, aucun port publié
docker compose exec serveur-mcp python -c "import httpx; print(httpx.get('http://calcul:80/api/sante').json())"
```

`requirements.txt` est exporté de `uv.lock` (`make lint` échoue s'il n'est pas à jour) :
`uv export --package agentinsurflow-calcul --no-emit-workspace --no-dev --no-hashes > fonction-calcul/requirements.txt`.
