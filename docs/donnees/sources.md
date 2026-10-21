# Inventaire des sources de données

*Livrable L1 · compétence C1. Spec §3.1, §5.3 ; CGU de l'API Légifrance (DILA, 15/12/2022).*

| | API Légifrance (REST) | Instantané JSON (fichier) | Dossiers de démonstration (base de données) |
|---|---|---|---|
| **Origine** | DILA, via la plateforme PISTE (bac à sable) | Sortie de la CLI d'extraction, versionnée dans `data/raw/` | Migration `Seed` d'`underwriting-admin` (données synthétiques) |
| **Contenu** | Code des assurances, périmètre auto : `L121-*`, `A121-1`, `L211-*`, `R211-*`, `A211-*` (S3-2) | Les mêmes articles, figés à une date (`code-assurances-2026-10-20.json`) + manifeste (date, périmètre, nb d'articles, sha256) | Souscripteurs, contrats, relevés, sinistres pour deux gestionnaires |
| **Format** | JSON (OAuth 2.0 `client_credentials`) | JSON | Tables PostgreSQL (base `dossiers`) |
| **Licence** | Licence Ouverte / Open Licence **Etalab 2.0** : citer la source et la date de mise à jour | Idem (dérivé de Légifrance) | Données inventées, aucune licence |
| **Données personnelles** | Aucune (textes de loi) | Aucune | Fictives mais au format personnel (nom, adresse, permis) → **exposées seulement par la vue minimisée** |
| **Contraintes** | Quotas PISTE par seconde, minute et jour (🔴 valeurs) ; bac à sable possiblement en retard sur Légifrance ; identifiants dans le `.env` local seulement | Rejouable sans réseau ni identifiants ; à régénérer quand le texte change | Accès en lecture par le compte `dossiers`, contrôle BOLA par `gestionnaire_id` |
| **Rôle** | Source primaire | Source de rejeu (CI, démo) | Ancrage SQL de l'agent (`numero_contrat`) |

**Attribution Etalab** : chaque article cité expose son attribution (concédant DILA, licence, lien vers
l'original, date d'extraction, mention des modifications) via `GET /api/documents/{doc_id}/attribution`.

**Reportés au rapport de certification** : le **scraping** (la source utile, Légifrance, offre une API
officielle sous licence ouverte : le scraping n'apporterait rien ici) et le **big data** (volume du corpus : quelques centaines
d'articles, sans besoin de traitement distribué).
