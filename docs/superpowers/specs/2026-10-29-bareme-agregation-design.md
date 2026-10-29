# Barème citable (#99) et jeu de données agrégé unique (#52) — conception

*29/10/2026 · issues #99 (C3, C4) et #52 (C3) · échéance : examen blanc du 30/10, livré **jusqu'en production**.*

## Intention

GF5 n'accepte un REFUS que si la fiche cite une source dont le `regle_id` est une règle déclenchée par le
barème. Ces règles vivent dans le code de `fonction-calcul` ; les 6 procédures `rag/corpus/procedures_internes/`
en recopient aujourd'hui le motif **à la main** : rien ne garantit qu'elles suivent le barème.

- **#99** : le contenu « barème » des procédures (identifiant, condition, seuil, effet, motif, version) est
  **généré** depuis la source de vérité du calcul, via un instantané versionné ; un test casse si le barème
  et le corpus divergent.
- **#52** : toutes les sources existantes sont fusionnées par **un script** en **un seul jeu de données
  brutes** nettoyé et normalisé, et c'est ce jeu qui alimente l'ingestion (locale, CI, déploiement).

Preuves visées : C3 (script d'agrégation, nettoyage, homogénéisation, documentation) et C4 (jeu normalisé,
script versionné et documenté, tests).

## Décisions prises par l'utilisateur

1. **Fusion** : un seul document par `regle_id`. Les champs du barème sont générés ; le texte métier
   rédigé (pièces à vérifier, fondement, information du demandeur, décision) est **conservé**.
2. **Table déclarative** dans `fonction-calcul/agentinsurflow_calcul/domain/bareme.py`, lue à la fois
   par `evaluer()` et par le générateur. Refonte acceptée, redéploiement de la Function compris.
3. **Sources de #52 = sources existantes** : instantané Légifrance (`data/raw/code-assurances-*.json`),
   instantané du barème (#99), documents rédigés (`rag/corpus/notices_produits`,
   `rag/corpus/procedures_internes`). Scraping (#45) et big data (#51) restent reportés au rapport,
   comme le dit `docs/donnees/sources.md`. Les dossiers SQL n'entrent pas.
4. **Le jeu unique alimente l'ingestion** : `make ingest` et `deploy.yml` le consomment à la place des trois
   appels actuels (`deploy.yml` l. 520-522).
5. **Les articles abrogés restent** dans le jeu brut (12 sur 119 dans l'instantané du 27/10). L'agrégation
   n'écarte que les entrées corrompues ; le serveur continue de filtrer l'état (`non_en_vigueur`).
6. **Livraison jusqu'en production avant l'examen** (release + `deploy.yml`, comme les v0.6.x).

## Non-objectifs

- Pas de scraping, pas de Spark, pas de fichier tabulaire nouveau (#45, #51).
- Pas de changement de schéma en base : `regle_id` est déjà stocké (migration `0003_regle_id`) → modèle
  Merise inchangé (à dire explicitement dans la doc, case C4 de #52).
- Pas de changement de la logique du barème : mêmes règles, mêmes seuils, mêmes motifs, même
  `VERSION_BAREME = "bareme-2026.10-v1"`. Les résultats d'`evaluer()` sont identiques avant/après.
- Pas de nouvelle dépendance.

## Anti-objectifs (échec même si « ça marche »)

- Perdre le texte métier des procédures (fondement, articles cités) : GF5 et la démo citent ce texte.
- Deux documents pour un même `regle_id`.
- Un paquet (`rag`) qui importe le code Python de l'autre (`fonction-calcul`) : le lien passe par le
  fichier d'instantané, jamais par un import.
- Un déploiement qui casse l'ingestion de production la veille de l'examen : le jeu agrégé doit produire
  en production le même corpus que les trois appels actuels (mêmes `doc_id` ; seules les procédures
  changent de `version`).
- Dupliquer le nettoyage déjà écrit côté serveur (`rag/agentinsurflow_rag/domain/corpus.py::nettoyer`).

## Partie 1 — #99 : barème citable

### Table déclarative

`bareme.py` expose une table `REGLES`, lue par `evaluer()` et par le générateur. Chaque règle porte :
`regle_id`, `libelle` (titre court : « Suspension de permis »), `conditions` (une **ou plusieurs**
conditions `(champ, opérateur, seuil)` combinées par ET — R06 en a deux : `anciennete_permis_mois < 36`
et `puissance_fiscale_cv > 7`), `motif` (texte actuel, inchangé), `effet` (`REFUSE` pour les six).
L'ordre R01→R06 est conservé. Les contrôles « donnée absente → `DonneeHorsBareme` » et `verifier_crm`
restent tels quels. Les tests existants de `fonction-calcul/tests/unit/test_bareme.py` doivent passer
sans modification : c'est le filet de la refonte.

### Instantané versionné

Une commande (dans `fonction-calcul`, `make bareme` — nom au choix du constructeur) écrit
`data/raw/bareme-2026.10-v1.json` : un manifeste (`version_bareme`, `regles` = 6, `sha256` du JSON
canonique des règles, même calcul que `sha_articles` de la CLI d'ingestion, date) et la liste des règles
sérialisées (seuils en texte : `"1.25"` pour le CRM, pas de float). Le nom du fichier est la version du
barème : un changement de version produit un nouveau fichier, l'ancien reste. Écriture atomique (fichier
temporaire puis `os.replace`), comme `sauvegarder_instantane`.

### Procédures fusionnées

Les fichiers `rag/corpus/procedures_internes/R0x_*.md` deviennent la **partie rédigée** seule : en-tête
réduit à `regle_id` (clé de jointure), puis les sections métier (pièces, fondement, décision, information
du demandeur). L'en-tête complet (`doc_id = PI-<regle_id>`, `version`, `article`, `date_debut`) et la
section « Règle » (condition lisible, seuil, motif entre guillemets, effet, version du barème) sont
**générés** depuis l'instantané au moment de l'agrégation. `doc_id` inchangé ; `version` devient liée au
barème (ex. `PI-R01_SUSPENSION-bareme-2026.10-v1`) → une nouvelle version par procédure à la prochaine
ingestion, ce qui est voulu par l'issue. La phrase « barème bareme-2026.10-v1 » écrite à la main dans la
section « Décision » doit venir de l'instantané, pas du texte rédigé.

### Tests (#99)

- Chaque `regle_id` de l'instantané a **exactement un** document généré, et chaque procédure rédigée a
  une règle (pas d'orpheline dans un sens ni dans l'autre).
- La version de l'instantané présent dans `data/raw/` = `VERSION_BAREME` du code, et l'instantané
  régénéré = l'instantané versionné (même sha256) : changer le barème sans régénérer casse le test.
- `evaluer()` : tests existants inchangés et verts.

## Partie 2 — #52 : jeu de données agrégé unique

### Script

Un script d'agrégation dans le paquet `rag` (CLI à côté de `cli/ingest.py`, commande `make agreger`) lit
les trois sources et écrit **un fichier** versionné + manifeste. Proposition (au constructeur d'ajuster) :
`data/aggregated/corpus-<date>.jsonl` (une entrée par ligne) et son manifeste (date, sha256, nombre
d'entrées par source et par collection, sha256 des instantanés d'entrée, nombre d'écarts par raison).

Enchaînement : ① lire l'instantané Légifrance le plus récent (vérifier son sha256, comme
`lire_instantane`) ; ② lire l'instantané du barème et générer les 6 procédures fusionnées ; ③ lire les
notices Markdown (`lire_markdown` existant) ; ④ normaliser chaque entrée au **même schéma** ;
⑤ écarter les corrompues avec leur raison ; ⑥ refuser les `doc_id` en double ; ⑦ écrire atomiquement.

### Schéma commun d'une entrée

Les champs que l'API `POST /api/ingestions` attend déjà (`doc_id`, `version`, `article`, `date_debut`,
`etat`, `texte_html`, `url_source`, `regle_id`), plus `collection` (une des trois) et `source`
(`legifrance`, `bareme`, `redige`). Ne rien inventer de plus.

### Nettoyage et homogénéisation

- **Entrées corrompues** (partielles, vides, trop courtes, date invalide) : écartées par la fonction
  existante `domain/corpus.py::nettoyer` (règle réutilisée, pas réécrite) ; raison consignée dans le
  rapport/manifeste. **Exception** : `non_en_vigueur` n'est **pas** un motif d'écart à l'agrégation
  (décision 5).
- **Formats** : dates en ISO `AAAA-MM-JJ`, numéros d'article via `normaliser_numero`, `etat` en
  majuscules, espaces superflus retirés, `regle_id` vide → `null`. Le texte reste dans `texte_html` tel
  que la source le donne (HTML Légifrance, Markdown rédigé) : le serveur le convertit déjà
  (`html_vers_texte`) ; le documenter comme choix.
- Le nettoyage serveur reste en place (défense en profondeur) : il n'a simplement plus rien de corrompu
  à rejeter, sauf les abrogés.

### Ingestion

`cli/ingest.py` accepte le jeu agrégé (option nouvelle, ex. `--jeu data/aggregated/corpus-<date>.jsonl`),
le regroupe par `collection` et envoie chaque collection comme aujourd'hui (lots de 50, une preuve
`eval/preuves/` par collection ou une preuve cumulée — au constructeur). `INSTANTANE` et `SOURCE` restent
utilisables (rétrocompatibilité locale). `deploy.yml` remplace ses trois `make ingest` par
`make agreger` (sans réseau ni identifiant) puis un seul `make ingest … JEU=…`. Le jeu agrégé est
versionné dans le dépôt (comme `data/raw/`) **et** régénéré au déploiement ; le constructeur choisit si le
déploiement ingère le fichier versionné ou le régénéré, en vérifiant qu'ils sont identiques.

### Tests (#52)

- Unitaire : une entrée partielle / vide / à date invalide est écartée avec sa raison ; une date non ISO
  ou un numéro non normalisé ressort homogénéisé ; un abrogé est conservé ; deux `doc_id` identiques →
  erreur.
- Sur les vraies sources : le jeu contient 119 entrées Légifrance (moins les corrompues, a priori 0)
  + 4 notices + 6 procédures, et chaque collection a le bon nombre d'entrées.
- Intégration existante (`rag/tests/integration/test_cli_ingest.py`) étendue : ingérer le jeu agrégé
  donne le même corpus que les trois appels séparés ; rejouer donne « 0 inséré ».

## Documentation

- `docs/donnees/pipeline.md` : section « Agrégation » = spécifications techniques, règles d'agrégation
  par source, choix de nettoyage et d'homogénéisation, dépendances, commandes (`make bareme`,
  `make agreger`, `make ingest JEU=…`), enchaînement, et « modèle Merise inchangé (regle_id déjà
  stocké) ».
- `docs/donnees/sources.md` : ajouter l'instantané du barème comme source.
- `rag/corpus/README.md` : expliquer que les procédures sont la partie rédigée, la partie barème étant
  générée.

## Livraison

PR unique fermant #99 et #52, CI verte, puis release et `deploy.yml` jusqu'en production avant l'examen
du 30/10 (prod actuelle : v0.6.24). Vérifications après déploiement : version de la Function de calcul,
rapport d'ingestion de production (6 nouvelles versions de procédures, 0 rejet hors abrogés), un
`/api/extraits` qui renvoie une procédure avec son `regle_id`. Les commandes `az` d'écriture se lancent à
la main (habitude du projet).

## Choix du rédacteur (issus de la relecture, à vérifier par l'utilisateur)

1. **`SOURCE` pour les procédures** : `--source rag/corpus/procedures_internes` n'est plus accepté
   (l'en-tête rédigé ne porte que `regle_id`) ; la CLI répond par un message qui renvoie vers
   `make agreger` puis `make ingest JEU=…`. `SOURCE` reste valable pour `notices_produits`, `INSTANTANE`
   pour Légifrance. Le test d'intégration qui ingère ce dossier passe par le jeu agrégé.
2. **Déterminisme** : aucune date du jour dans le contenu.
   - `date_debut` des procédures = une constante `DATE_BAREME` (2026-10-26) de la table, sérialisée dans
     l'instantané.
   - `article` = `PI-` + `regle_id` avec `_` → `-` (ex. `PI-R06-JEUNE-PERMIS-PUISSANCE`, valeur actuelle).
   - Le sha256 de l'instantané ne couvre que les règles ; le manifeste ne porte pas de date de génération.
   - Le jeu agrégé est nommé d'après la date de l'instantané Légifrance utilisé :
     `data/aggregated/corpus-<date Légifrance>.jsonl`.
   - Régénérer = même fichier, octet pour octet. C'est ce que vérifient le test et `deploy.yml`.
3. **`nettoyer` et les abrogés** : dans `nettoyer`, le contrôle de date passe **avant** le contrôle
   d'état (petit réordonnancement, tests serveur à ajuster si l'un dépend de l'ordre). L'agrégation
   appelle `nettoyer` comme **juge** : un `Rejet` `non_en_vigueur:*` garde l'entrée, tout autre `Rejet`
   l'écarte. Elle reprend `article` et `date_debut` normalisés de l'`ArticlePropre`, mais écrit le
   `texte_html` d'origine (pas le texte converti).
4. **Gabarit des procédures rédigées** :
   - **Contenu du fichier rédigé** : en-tête `regle_id`, puis les sections à partir de « Pièces à
     vérifier ».
   - **Partie générée en tête** : en-tête complet, titre `# Procédure interne <regle_id> — <libellé>`,
     mention « Document fictif… », section « Règle » (condition lisible, seuil, motif, effet).
   - **Version du barème dans la section « Décision »** : elle passe par un marqueur `{version_bareme}`
     dans le texte rédigé, remplacé à la génération. Un marqueur inconnu ou resté non remplacé → erreur.
5. **Où vivent les tests** :
   - **Côté `fonction-calcul/tests/unit`** : « instantané régénéré = instantané versionné » et
     « version de l'instantané = `VERSION_BAREME` ». Le chemin `data/raw/` est résolu depuis la racine
     du dépôt, que la CI extrait en entier.
   - **Côté `rag/tests`** : « un document par `regle_id` », les volumes 119 + 4 + 6 et le nettoyage.
     Ces tests lisent **le fichier** JSON, sans import de `fonction-calcul`.
   - **Côté déploiement** : la Function de calcul n'a pas besoin de `data/raw/` dans son zip.
     L'agrégation tourne dans le job d'ingestion, qui a le dépôt complet.

## Laissé au constructeur

Noms exacts des commandes et des options, emplacement du script dans `rag`, format d'une condition dans la
table (tuple, dataclass), rendu lisible de la condition (« au moins 2 », « plus de 1,25 »), forme de la
preuve d'ingestion, découpage en commits.
