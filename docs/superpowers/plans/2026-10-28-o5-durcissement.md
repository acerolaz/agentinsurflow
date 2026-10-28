# O5 Durcissement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** Rendre le contrat personnel cohérent (bilan, preuves), reporter P45 dans le dossier, tenir la grille de retours des ateliers, corriger les commentaires périmés de `make up`. Aucune nouvelle fonction.

**Architecture :** Documentation seulement (`docs/`, `README.md`). Les preuves en staging (K1, K2, K6, K9) et les fusions #145 à #147 sont **manuelles** et attendent la fin du gel ou S1 : elles sont la Task 4, non dispatchée.

**Tech Stack :** Markdown ; `pypdf` lancé ponctuellement (`uv run --no-project --with pypdf python -I`) pour citer `Brief5/dossier-conception-v1.2.pdf`, sans dépendance ajoutée.

**Spec :** `docs/superpowers/specs/2026-10-28-o5-durcissement-design.md` (issue #156).

## Global Constraints

- Un K ne passe « tenu » que si une preuve existe dans `eval/preuves/` ; aucun K n'est promu par ce plan.
- Rien d'inventé : une citation vient du PDF ou d'un fichier du dépôt ; sinon « non consigné » (grille) ou « à vérifier dans le PDF » (amendement).
- La grille consigne aussi ce qui a été refusé ; on ne réécrit pas l'historique.
- C5 et C6 restent `🔴` (absents du référentiel).
- Gel du 29/10 au matin à la fin de la démo du 30/10 : PR en brouillon, aucune fusion.
- Ne pas toucher aux dossiers de démo 000001, 000003, 000004, 000010 ni aux dossiers 000007 à 000009 (CI).
- Français partout.

## Review Focus

1. Le bilan compte des statuts différents du tableau → `make test` ne le voit pas : le relecteur recompte les colonnes « Statut » de K1 à K11.
2. Une citation du PDF est paraphrasée au lieu d'être recopiée → le relecteur la retrouve dans l'extraction pypdf.
3. Une ligne de la grille porte une décision ou un statut absent des sources → « non consigné » attendu.
4. Le comportement « hors barème » (K1) n'aboutit pas à une revue humaine motivée → une issue est ouverte, le contrat le signale, aucune preuve n'est écrite.
5. Un renvoi pointe vers un fichier qui n'existe que sur une branche non fusionnée (D106 sur #167, D42 sur #168) → la PR est citée, pas un lien mort.

---

### Task 1 : Contrat personnel cohérent, K1 vérifié, commentaires de `make up`

**Files :**
- Modify : `docs/contrat-personnel.md` (bilan, l. 25 ; la mention historique « K6 (avenant) » ; ligne K1), `README.md` (l. 121 et 167), `docs/donnees/modele.md` (l. 149)

- [ ] **Step 1 : bilan.** Écrire « **Bilan** : 7 tenus (K3, K4, K5, K7, K8, K10, K11), 4 en cours (K1, K2, K6, K9), 0 avenant. », recompté sur le tableau. La mention historique « K6 (avenant) » est conservée si elle date une décision passée, avec la précision qu'elle n'est plus en vigueur (K6 est en cours depuis l'UI, #134).
- [ ] **Step 2 : K1, vérifier le comportement réel « hors barème ».** Lire le domaine du calcul (`DonneeHorsBareme`), l'outil MCP qui l'appelle et la Saga du cluster (Analyste, revue humaine), ainsi que `agentic-cluster/tests/unit/test_agents.py::test_hors_bareme_risque_limite_section_remplie_repli`. Répondre à la question : un dossier hors barème aboutit-il à `REVUE_HUMAINE` **avec un motif** lisible par le gestionnaire ?
  - Oui : ajouter à la ligne K1 le chemin du code et des tests qui le prouvent, ainsi que le dossier proposé pour la recette en staging. Ce dossier est hors de 000001, 000003, 000004, 000007 à 000010 ; s'il n'en existe pas, un seed est à créer dans la Task 4. K1 reste « en cours ».
  - Non : ouvrir une issue (`gh issue create`, titre « K1 : un dossier hors barème n'aboutit pas à une revue humaine motivée », avec le constat et les fichiers) et la citer dans la ligne K1.
- [ ] **Step 3 : `make up`.** Remplacer les trois commentaires qui ne listent que 4 services par la liste du Makefile (`up:`, l. 49) : postgres, rag (:8001), underwriting-admin (:8002), serveur MCP, cluster d'agents, calcul, gateway (:8000).
- [ ] **Step 4 : `make test`, `make lint`.** Commit `docs(contrat): bilan 7/4/0, K1 hors barème vérifié, make up à 7 services (#156)`.

### Task 2 : Amendement P45 et regroupement des amendements

**Files :**
- Create : `docs/dossier/amendements-p45.md`, `docs/dossier/amendements.md` (index)

- [ ] **Step 1 : extraire du PDF** (pypdf) le §10.1 (écarts : .NET 10, underwriting-admin en C#, GitHub Actions), ainsi que les sections L5 et L11 visées par P45 (p. 55 : « Reporter dans L5 / L11 les écarts du §10.1 … — Acerola »).
- [ ] **Step 2 : `amendements-p45.md`**, au format de `amendements-d42.md` sur #168 (section · texte actuel · texte corrigé) : une ligne par endroit de L5 et L11 à corriger, avec le texte actuel recopié tel quel et le texte corrigé reprenant l'écart du §10.1. Un passage introuvable porte « à vérifier dans le PDF ».
- [ ] **Step 3 : `amendements.md`**, un index de quelques lignes : D106 (PR #167, `amendements-d106.md`), D42 (PR #168, `amendements-d42.md`) et P45 (ce fichier). Les deux premiers fichiers sont cités par leur PR tant qu'elle n'est pas fusionnée.
- [ ] **Step 4 : `make lint`.** Commit `docs(dossier): amendement P45 et index des amendements (#156)`.

### Task 3 : Grille de retours des ateliers

**Files :**
- Create : `docs/grille-retours.md`

- [ ] **Step 1 : relever les sources** :
  - `docs/demo-atelier.md`, `docs/demo-atelier-3.md`, `docs/demo-atelier-4.md` ;
  - `../../brief1/grille-atelier-1-cadrage.pdf`, `../../brief2/grille-atelier-2-socle-chaine.pdf`, `../../brief3/grille-atelier-3-donnees-ancrage.pdf`, lus avec pypdf ;
  - les issues et PR qui citent un atelier (`gh issue list --state all --search atelier`, `gh pr list --state all --search atelier`).
- [ ] **Step 2 : écrire la grille**, avec un tableau par atelier (1 à 5) aux colonnes : date · relecteur · retour · décision · issue ou PR · statut.
  - Chaque cellule vient d'une source citée en pied de tableau ; une cellule sans source porte « non consigné ».
  - Les retours refusés restent dans la grille, avec leur décision.
  - L'atelier 5 n'a qu'une ligne : sa date si elle est écrite quelque part, sinon « non consigné », et « à remplir pendant l'atelier » (la grille `grille-atelier-5-vigie-demo.pdf` n'a pas été fournie).
- [ ] **Step 3 :** renvoi depuis `docs/contrat-personnel.md` (une ligne). Commit `docs: grille de retours des ateliers 1 à 5 (#156)`.

### Task 4 : Manuel (Acerola) — non dispatchée

- Après la démo du 30/10 : fusionner #145, #146 et #147, dans cet ordre, une fois leur CI verte. Leurs délais (calcul 20 s, MCP 22 s, Actuaire 4 s) sont alors livrés.
- Fin du gel : jouer en staging le dossier hors barème (K1), puis consigner le résultat dans `eval/preuves/`.
- Après le déploiement de #147 : vérifier « Tchat corpus » au clavier (K6), puis consigner.
- Après S1 en staging :
  - K2 : prouver d'abord par `GET /api/traces/{trace_id}` et une requête SQL, puis en KQL ;
  - K9 : montrer l'Application Map, Transaction Diagnostics, Live Metrics et une requête KQL sur `audit.agent`.
- À chaque preuve : recompter le bilan.
- Point 8 (`evals-pr`, limite connue) : il relève de `docs/exploitation.md` (S3, PR #163). Vérifier qu'il y est cité.
