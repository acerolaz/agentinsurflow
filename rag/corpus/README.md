# Corpus rédigé pour le projet

Documents **fictifs**, rédigés pour AgentInsurFlow (droits détenus par le projet) : ils ne viennent pas de Légifrance et n'ont pas d'attribution Etalab.

- `notices_produits/` : un contrat type par formule ; `doc_id` = la formule du contrat (`tiers`, `tiers_etendu`, `tous_risques`), que le Rédacteur reprend comme `contrat_type` (garde-fou GF6). `jeunes_conducteurs` n'est pas une formule : notice complémentaire, citable comme appui, jamais comme `contrat_type`.
- `procedures_internes/` : une procédure par règle du barème (`fonction-calcul/.../bareme.py`) ; `regle_id` relie la procédure à la règle, ce que vérifie le garde-fou GF5 sur un refus.

Chaque fichier commence par un en-tête `cle: valeur` entre deux lignes `---` : `doc_id`, `version`, `article`, `date_debut`, et `regle_id` pour une procédure. Changer le texte impose une nouvelle `version`.

Ingestion : `make ingest URL=<gateway> COLLECTION=notices_produits SOURCE=rag/corpus/notices_produits` (idem pour `procedures_internes`) ; le déploiement le fait à chaque révision.
