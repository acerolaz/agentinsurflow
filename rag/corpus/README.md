# Corpus rédigé pour le projet

Documents **fictifs**, rédigés pour AgentInsurFlow (droits détenus par le projet) : ils ne viennent pas de Légifrance et n'ont pas d'attribution Etalab.

- `notices_produits/` : un contrat type par formule ; `doc_id` = la formule du contrat (`tiers`, `tiers_etendu`, `tous_risques`), que le Rédacteur reprend comme `contrat_type` (garde-fou GF6). `jeunes_conducteurs` n'est pas une formule : notice complémentaire, citable comme appui, jamais comme `contrat_type`.
- `procedures_internes/` : la **partie rédigée** d'une procédure par règle du barème. Le titre, la mention « Document fictif », l'en-tête complet et la section `## Règle` sont **générés** depuis `fonction-calcul/.../bareme.py` (`rag/.../domain/procedures.py`) ; le fichier ne garde que `regle_id` en en-tête et le texte métier à partir de `## Pièces à vérifier`. Le marqueur `{version_bareme}` y est remplacé à la génération. `regle_id` relie la procédure à la règle, ce que vérifie le garde-fou GF5 sur un refus.

Une notice commence par un en-tête `cle: valeur` entre deux lignes `---` : `doc_id`, `version`, `article`, `date_debut`. Changer le texte impose une nouvelle `version`.

Ingestion : `make bareme` (si le barème change), `make agreger`, puis `make ingest URL=<gateway> JEU=data/aggregated/corpus-<date>.json` ; le déploiement agrège et ingère à chaque révision.
