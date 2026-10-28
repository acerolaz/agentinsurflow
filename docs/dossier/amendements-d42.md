# Amendement au dossier de conception (V1.2) — décision D42

**D42 passe de V2 au sprint 5.** Le GLM de Poisson de fréquence (freMTPL2, fiche `fonction-calcul/agentinsurflow_calcul/modeles/glm-freq-20261028-v1.md`) est livré au sprint 5, en comparaison seulement : il n'entre ni dans la décision, ni dans la prime, ni dans le rapport de l'Actuaire.

Source : `dossier-conception-v1.2.pdf` (hors dépôt), texte extrait le 28/10.

| Section | Texte actuel | Texte corrigé |
|---|---|---|
| p. 8, tableau du périmètre | « GLM Poisson (C12/C13) — Pipeline d'entraînement hors budget V1 (D42) — V2 » | « GLM Poisson (C12/C13) — Livré au sprint 5 en comparaison seulement (`POST /api/calcul/frequence`), porte de qualité en CI (D42) — Sprint 5 » |
| p. 35, planning | « En V2, hors de ce plan : implémentation de la chaîne CI/CD + LLMOps du L7 D56, GLM Poisson D42, configuration des alertes » | « En V2, hors de ce plan : implémentation de la chaîne CI/CD + LLMOps du L7 D56, configuration des alertes. Le GLM Poisson (D42) est livré au sprint 5. » |
| p. 36, questions du jury, Q10 « Où est le modèle entraîné exigé par C12 ? » | « Le GLM Poisson arrive en V2, comme seconde implémentation du même outil » | « Le GLM Poisson est livré au sprint 5, à côté du barème : `/api/calcul/frequence`, fiche du modèle, porte de qualité et réentraînement en CI (job `modele`, C13) » |

Regrouper cet amendement avec ceux de S4 (D106), comme le prévoit la spec O5.
