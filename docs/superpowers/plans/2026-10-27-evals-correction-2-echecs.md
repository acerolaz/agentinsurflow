# Evals · correction des 2 échecs connus (#50) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** faire passer `reference-exacte-a121-1` et `reference-exacte-l211-1` en staging (≥ 90 %, p95 ≤ 30 s) avant que le cluster (#7) ne touche aux prompts.

**Architecture:** l'annexe bonus-malus d'A121-1 est extraite de Légifrance puis **rattachée** à A121-1 (même `article`, même `doc_id`, texte ajouté à la suite) ; le prompt système demande une réponse courte qui résume au lieu de recopier. Aucun changement du plafond `LONGUEUR_MAX = 600` ni du golden.

**Tech Stack:** Python 3 / httpx (client Légifrance), pytest, GitHub Actions (job `evals` de `ci-cd.yml`).

**Spec:** issue mère #50 + décisions prises en conversation (27/10) : l'annexe va dans le corpus (pas d'ajustement du golden) ; rattachée à A121-1 sous la même référence ; L211-1 corrigé par une réponse plus courte, pas par le plafond.

## Global Constraints

- Branche unique `fix/evals-2-echecs` depuis `main` ; une PR qui ferme les sous-issues, la #50 est fermée après la preuve.
- Aucun changement de version (`pyproject.toml`) : le manifeste `X.Y.Z-build.N` et son tag `manifeste-*` sont posés par le job `release` quand les evals passent.
- Écritures Azure / staging (ingestion) : lancées **par Acerola**, pas par l'agent.
- Identifiants PISTE : `.env` local seulement, jamais affichés ni committés.
- Porte de la #50 : taux ≥ 90 % en staging, latence p95 ≤ 30 s, rapport versionné dans `eval/preuves/`.

## Review Focus

1. **Conflit de version à l'ingestion** : A121-1 existe déjà en staging avec la version `LEGIARTI000006785942` ; un texte modifié sous la même version est rejeté `conflit_version` (`domain/corpus.py:141`). L'entrée fusionnée porte donc la version composée `"<version article>+<version annexe>"` → `nouvelle_version`. Test : Task 1, `test_extraire_rattache_l_annexe_a_a121_1`.
2. **`url_source` de l'entrée fusionnée** : doit rester l'URL de l'article (`…/article_lc/<version article>`), pas une URL construite sur la version composée. Même test.
3. **Annexe sans article** (plan Légifrance sans A121-1, ou annexe hors périmètre) : l'annexe seule ne doit jamais sortir comme article autonome. Test : Task 1, `test_annexe_orpheline_ignoree`.
4. **Faux positifs du périmètre** : l'élargissement ne doit pas faire entrer `A121-10` ni une autre annexe du code. Task 1, cas ajoutés à `test_perimetre`.
5. **Ordre de déploiement** : le job `evals` tourne juste après le déploiement de staging, sans ingestion ; l'instantané doit être ingéré en staging **avant** le merge, sinon A121-1 échoue encore. Task 2, étape d'ingestion avant la PR.

---

### Task 0: Repérer l'annexe dans Légifrance (G0) — #124

Lecture seule ; aucune décision de code ne se prend avant ce résultat.

- [ ] **Step 1 : Acerola lance la sonde** (identifiants PISTE du `.env`) depuis `brief2/src` :

```bash
uv run python -c "
import httpx
from agentinsurflow_rag.infrastructure.legifrance.client import TEXT_ID, ConfigLegifrance, _articles_du_plan, appeler, jeton_piste
cfg=ConfigLegifrance(); c=httpx.Client(timeout=60); j=jeton_piste(c,cfg)
p=appeler(c,'/consult/code/tableMatieres',{'textId':TEXT_ID,'date':'2026-10-27','nature':'CODE'},j,cfg=cfg)
print([(a.get('num'),a.get('id')) for a in _articles_du_plan(p) if '121-1' in str(a.get('num'))])"
```

Expected : une ligne pour `A121-1` et une ligne pour son annexe (numéro attendu de la forme `Annexe art. A121-1`, à confirmer).

- [ ] **Step 2 : Consigner le numéro exact** de l'annexe dans la sous-issue. **Si l'annexe n'apparaît pas** dans la table des matières (annexe portée par `getArticle` d'A121-1, ou texte séparé) : arrêter et revenir vers Acerola, Task 1 est à redéfinir.

### Task 1: Rattacher l'annexe à A121-1 à l'extraction — #125

**Files:**
- Modify: `rag/agentinsurflow_rag/infrastructure/legifrance/client.py` (`PERIMETRE`, nouveau `ANNEXE_A121_1`, `rattacher_annexe`, `extraire`)
- Test: `rag/tests/unit/test_legifrance.py`

**Interfaces:**
- Consumes : numéro exact de l'annexe (Task 0), noté ci-dessous `NUM_ANNEXE`.
- Produces : `extraire(...)` renvoie au plus **une** entrée `article == "A121-1"`, dont `texte_html` = texte de l'article + texte de l'annexe, `version == "<v article>+<v annexe>"`, `doc_id` et `url_source` de l'article.

- [ ] **Step 1 : Tests en échec**

Dans `test_perimetre`, ajouter `(NUM_ANNEXE, True)` et `("Annexe art. A121-10", False)`.

```python
def test_rattacher_annexe() -> None:
    article = vers_article_entrant(ARTICLE_LF | {"num": "A121-1", "id": "V1", "cid": "C1", "texteHtml": "<p>art</p>"})
    annexe = vers_article_entrant(ARTICLE_LF | {"num": NUM_ANNEXE, "id": "V2", "cid": "C2", "texteHtml": "<p>clause</p>"})
    fusion = rattacher_annexe(article, annexe)
    assert fusion["article"] == "A121-1" and fusion["doc_id"] == "C1"
    assert fusion["version"] == "V1+V2"
    assert fusion["texte_html"] == "<p>art</p><p>clause</p>"
    assert fusion["url_source"] == "https://www.legifrance.gouv.fr/codes/article_lc/V1"


def test_extraire_rattache_l_annexe_a_a121_1() -> None:
    # plan : A121-1 (A3) et son annexe (A5) → une seule entrée A121-1, version "A3+A5"
    ...  # même harnais que test_extraire_ne_garde_que_le_perimetre
    assert [a["article"] for a in articles] == ["L211-1", "A121-1"]
    assert articles[1]["version"] == "A3+A5"


def test_annexe_orpheline_ignoree() -> None:
    # plan avec l'annexe mais sans A121-1 → aucune entrée pour l'annexe
    assert all(a["article"] != NUM_ANNEXE for a in articles)
```

- [ ] **Step 2 : Lancer** `uv run --directory rag pytest tests/unit/test_legifrance.py -q` → FAIL (`rattacher_annexe` absent, périmètre refuse l'annexe).

- [ ] **Step 3 : Implémenter**
  - `ANNEXE_A121_1 = normaliser_numero(NUM_ANNEXE)` ; `PERIMETRE` accepte aussi ce numéro normalisé (alternative exacte, ancrée, pas de motif générique « Annexe… »). Mettre à jour le commentaire `🔴 Task G0` de la ligne 23 (confirmé le 27/10).
  - `rattacher_annexe(article: dict[str, Any], annexe: dict[str, Any]) -> dict[str, Any]` : copie de `article` avec `texte_html` concaténé et `version` composée ; `url_source` inchangée.
  - `extraire` : après la boucle `getArticle`, retirer l'entrée dont `normaliser_numero(article) == ANNEXE_A121_1` et, si A121-1 est présent, la remplacer par `rattacher_annexe(...)` ; annexe orpheline : jetée.

- [ ] **Step 4 : Lancer** la même commande → PASS ; puis `make test` → vert.

- [ ] **Step 5 : Commit** `fix(rag): rattacher l'annexe bonus-malus à A121-1 à l'extraction (#50)`.

### Task 2: Nouvel instantané et ingestion en staging — #126

**Files:**
- Create: `data/raw/code-assurances-2026-10-27.json` (sortie de `make extraire`)
- Create: `eval/preuves/ingestion-2026-10-27-staging.json`

**Interfaces:** Consumes Task 1 (`extraire`).

- [ ] **Step 1 : Acerola lance** `make extraire` → nouveau fichier dans `data/raw/`.
- [ ] **Step 2 : Vérifier l'instantané** : une seule entrée `A121-1`, `version` contenant `+`, texte contenant la clause (`coefficient de réduction-majoration`) ; aucune entrée annexe autonome.

```bash
python3 -c "import json;a=[x for x in json.load(open('data/raw/code-assurances-2026-10-27.json'))['articles'] if 'A121-1' in x['article']];print(len(a),a[0]['version'],'réduction-majoration' in a[0]['texte_html'])"
```
Expected : `1 LEGIARTI…+LEGIARTI… True`.

- [ ] **Step 3 : Acerola ingère en staging, avant le merge** (le job `evals` n'ingère pas) : `APP_ENV=staging make ingest URL=<gateway staging> INSTANTANE=data/raw/code-assurances-2026-10-27.json`. Expected : `nouvelles_versions ≥ 1`, aucun rejet `conflit_version`. Le rapport est la preuve `eval/preuves/ingestion-2026-10-27-staging.json` (nom **avec** l'environnement).
- [ ] **Step 4 : Commit** de l'instantané et de la preuve : `feat(corpus): instantané du 27/10 avec l'annexe d'A121-1 (#50)`.

### Task 3: Réponses plus courtes — #127

**Files:**
- Modify: `rag/agentinsurflow_rag/prompts/systeme.md:5`

- [ ] **Step 1 : Remplacer la ligne 5** par :

```text
Réponds en français, en trois phrases courtes au plus (600 caractères au maximum) : résume les articles, ne recopie pas leur texte.
```

- [ ] **Step 2 : Vérifier en local** (pile `make up`, instantané de Task 2 ingéré en local) : `make eval URL=http://localhost:8000` → `reference-exacte-l211-1` et `reference-exacte-a121-1` sans échec `longueur` ni `articles`. Si L211-1 dépasse encore : revenir vers Acerola avant de toucher autre chose (pas de hausse de `LONGUEUR_MAX`).
- [ ] **Step 3 : Commit** `fix(rag): réponse résumée de 600 caractères au plus (#50)`.

### Task 4: Evals de staging, preuve et manifeste — #128

**Files:**
- Create: `eval/preuves/evals-2026-10-XX.json`
- Modify: `README.md:64-65` (taux d'evals et échecs connus)

- [ ] **Step 1 : PR en brouillon** `fix/evals-2-echecs` → `main` (« Closes #124, #125, #126, #127 » ; #128 se ferme avec la preuve), CI verte, merge par Acerola.
- [ ] **Step 2 : Suivre le run de `main`** : job `evals` vert (les déclencheurs `data/raw/` et `prompts/` relancent les evals), puis `release` pose le tag `manifeste-<X.Y.Z>-build.<N>`.
- [ ] **Step 3 : Verser la preuve** : `gh run download <id> -n evals-staging-<sha>` → `eval/preuves/evals-2026-10-XX.json`. Vérifier : taux ≥ 0,90 (≥ 10/11), p95 ≤ 30 s, aucun échec sur les deux cas. Taux entre 0,80 et 0,90 : la porte CI passe mais la #50 non → revenir vers Acerola.
- [ ] **Step 4 : README** : remplacer la phrase « 81,8 % … deux échecs connus » par le nouveau taux, la p95 et le tag de manifeste ; commit `docs: evals de staging après #50`, PR, merge ; fermer la #50.
- [ ] **Step 5 : Production** : l'ingestion du nouvel instantané en production reste à faire par Acerola après la release (hors porte de la #50, à noter dans la sous-issue).
