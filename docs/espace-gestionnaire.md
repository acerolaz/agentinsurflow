# Espace gestionnaire

Page HTML + JavaScript sans étape de build, servie par la gateway sous **`/app/`** (Swagger garde la racine). Spec : [`superpowers/specs/2026-10-27-espace-gestionnaire-design.md`](superpowers/specs/2026-10-27-espace-gestionnaire-design.md) ; issues #103, #104, #101, #129, #130.

## Écrans et routes

| Écran | Ce qu'il fait | Routes (par la gateway) | Portée |
|---|---|---|---|
| Connexion | Cartes « Gestionnaire A » / « Gestionnaire B » : le choix préremplit l'UPN (`loginHint`), Entra authentifie | Entra (redirection vers `/app/`) | — |
| Mes dossiers | Portefeuille du gestionnaire connecté (BOLA) | `GET /api/contrats` | underwriting |
| Dossier | Fiche du lead, Lancer / Reprendre, Pause, frise, détail d'une étape (tokens compris), pièces manquantes, relance et classement sans suite, proposition et revue, contrat | `POST /v1/souscriptions/{n}/evaluation`, `…/pause`, `…/revue` ; `GET /api/contrats/{n}/etat`, `GET /api/contrats/{n}/souscripteur`, `POST /api/contrats/{n}/relances`, `POST /api/contrats/{n}/sans-suite`, `GET /v1/souscriptions/{n}/contrat`, `GET /api/traces/{trace_id}` | cluster ; underwriting |
| Tchat corpus | Question libre, réponse et sources (lien Légifrance quand l'extrait en porte un) | `POST /api/reponses` | rag |

Pictogrammes décoratifs (emoji, `aria-hidden`) sur l'en-tête, les agents de la frise, les sous-onglets et les actions ; le contrat imprimé n'en porte aucun.

## Procédure de démo (30/10)

0. **Aucun déploiement après la préparation** : les bases de staging et de production sont éphémères, chaque déploiement remet les dossiers au seed.
1. `https://<gateway>/app/` → choisir **A** → « Se connecter avec Microsoft ».
2. **Mes dossiers** → ouvrir le dossier 1 (acceptable) : la fiche du lead s'affiche en tête → **Lancer l'évaluation** : la frise avance chaque seconde ; cliquer une étape terminée montre son mode, sa durée et ses tokens.
3. Pendant l'évaluation, **Pause** : elle s'arrête après l'agent en cours (`EN_PAUSE`) → **Reprendre**.
4. **Contrat proposé** : lire fiche et prime → motif → **Valider** → contrat généré → **Imprimer**.
5. Dossier 3 (sans relevé) → **Lancer** → **Pièces manquantes** : modifier le mail → **Envoyer la relance** (« Relance 1/3 enregistrée… »).
6. Dossier 10 (refus R01) → **Lancer** → proposition de refus → **Refuser** avec un motif.
7. **Tchat corpus** : « Quelles pièces pour souscrire une assurance auto ? » → réponse et sources.
8. Se déconnecter, se connecter en **B** : le dossier de A est introuvable (même 404 qu'un dossier inexistant).

## Commandes à lancer par Acerola

Écritures Entra et variables GitHub : jamais lancées par un agent.

```bash
make entra DEMO_USER_ID=<oid de A>                         # rôles de A (rag, underwriting, mcp, cluster) et redirections /app/
gh variable set SEED_GESTIONNAIRE_A --body <oid de A>
gh variable set SEED_GESTIONNAIRE_C --body <oid de l'identité de la CI>
gh variable set ESPACE_COMPTE_A --body <UPN de A>          # facultatif : préremplit la connexion
gh variable set ESPACE_COMPTE_B --body <UPN de B>
gh variable set E2E_CONTRAT_PROPRE --body AIF-2026-000007
gh variable set E2E_CONTRAT_HOSTILE --body AIF-2026-000008
gh variable set E2E_CONTRAT_PAUSE --body AIF-2026-000009
```

Puis redéployer (fusion sur `main` ou `deploy.yml` lancé à la main) : la base annexe est éphémère et repart des migrations, donc du seed avec les nouveaux `SEED_GESTIONNAIRE_*` ([`rollback.md`](rollback.md), « Base annexe éphémère »).

## Fichiers

| Fichier (`gateway/src/AgentInsurFlow.Gateway.Api/wwwroot/app/`) | Rôle |
|---|---|
| `index.html`, `app.css` | Coquille, deux thèmes par variables (`data-theme` sur `<html>`) |
| `app.js` | Routeur sur le fragment (`#/dossiers`, `#/dossiers/AIF-…`, `#/tchat`), en-tête à onglets, portefeuille, tchat |
| `dossier.js` | Vue d'un dossier (#104) |
| `auth.js` | MSAL en redirection (code + PKCE, client public) ; le choix A/B ne fait que préremplir `loginHint` |
| `api.js` | Appels à la gateway avec le jeton du service ; un 401 est réessayé une fois avec un jeton renouvelé, une coupure réseau rend le statut 0 (testés par `make espace-test` : `gateway/tests/espace/api.test.mjs`, #195) |
| `dom.js`, `logique.js` | Rendu sans `innerHTML` ; logique pure testée par `make espace-test` |
| `vendor/` | `msal-browser` versionné (version et SHA-384 dans `vendor/README.md`) |

Configuration publique, sans secret : `GET /app/config.json`, lue dans la section `Espace` de la gateway (`Espace__ClientId` à défaut `SWAGGER_CLIENT_ID`, `Espace__Authority`, `Espace__Scopes__Rag|Underwriting|Cluster`, `Espace__Comptes__A|B`).

## Sécurité

- CSP servie avec chaque fichier : `script-src 'self'`, `style-src 'self'`, `connect-src 'self' https://login.microsoftonline.com`, `frame-ancestors 'none'`. Aucun CDN ; `integrity` SRI sur MSAL (un TI vérifie qu'il correspond au fichier servi).
- Les jetons restent en `sessionStorage` (MSAL) ; chaque service revalide le jeton, la page n'est qu'un client.
- Tout texte venu d'un service est inséré par `textContent` ; un numéro de dossier hors `^AIF-\d{4}-\d{6}$` ne s'ouvre pas.
- Le filtrage des spans (« Outils appelés ») est un **affichage**, pas une protection : `GET /api/traces/{id}` rend tous les attributs de la trace au gestionnaire qui en connaît l'identifiant (128 bits, lu dans ses propres rapports). La vraie garde est en amont : aucune donnée personnelle n'entre dans un span (la relance n'y met que son rang et ses types de pièces).

## Accessibilité (RGAA 11.1 / WCAG 2.1.1)

Prévu dans le code :
- en-tête : liens de navigation dans un `<nav>`, chacun atteignable par Tab, `aria-current="page"` sur la page active (pas un `tablist` : ils changent de page) ;
- sous-onglets du dossier `role="tablist"`, passage aux flèches gauche/droite, `aria-selected` ;
- bouton de thème avec `aria-pressed` ; focus visible (`:focus-visible`) dans les deux thèmes ;
- connexion par `<input type="radio">` étiquetés dans un `fieldset` ;
- portefeuille : chaque numéro est un lien (Entrée l'ouvre) ;
- fil du tchat en `aria-live="polite"`, erreurs en `role="alert"`.

**Vérification au clavier seul** (à faire en local, `make up`, `http://localhost:8000/app/`) — *non faite par Claude : la connexion Entra est interactive.*

| Parcours | Résultat |
|---|---|
| Connexion A | à vérifier |
| Liens de l'en-tête au Tab | staging 28/10 : « Tchat corpus » inatteignable (onglet ARIA en `tabindex="-1"`) → liens simples, à revérifier après déploiement |
| Ouverture d'un dossier avec Entrée | staging 28/10 (000006) : OK, comme le lancement, les sous-onglets, le motif et la validation |
| Thème basculé puis gardé après rechargement | à vérifier |
| Question au tchat : réponse et sources | à vérifier |
| Dossier : lancer, frise qui avance chaque seconde, focus gardé sur « Pause » | à vérifier |
| Pause puis « Reprendre » : la frise repart de l'étape suivante | staging 27/10 (000005) : OK, même après redémarrage du cluster (K11) |
| Double clic sur « Lancer » : un seul appel, sinon message 409 | à vérifier |
| Valider avec un motif, contrat affiché puis « Imprimer » : conditions particulières sur le modèle d'Acerola (échéance, souscripteur, véhicule, garanties et franchises, cotisation, notice RGPD) et conditions générales (notice du contrat type) | staging 27/10 (000001) : OK, contrat imprimé, relu en `GET` ; visionneuse (#145) à vérifier |
| En tête du dossier : fiche du souscripteur (civilité, nom, prénom, adresse, mobile, e-mail, véhicule) ; 404 sur un dossier d'un autre gestionnaire | staging 27/10 : OK (fiche affichée ; 404 sur 000007) |
| Étape choisie : mode, cause, tokens (entrée + sortie, « aucun appel LLM » en repli), outils appelés | à vérifier |
| Dossier sans relevé : trois relances, la quatrième refusée ; `<b>x</b>` affiché littéralement | staging 27/10 (000003) : trois relances, plus de quatrième proposée ; `<b>x</b>` à vérifier |
| Après la troisième relance : « Classer sans suite », confirmation, statut `SANS_SUITE`, « Lancer l'évaluation » désactivé | staging 27/10 (000003) : OK |
| Motif de revue saisi, changement de sous-onglet puis retour : motif gardé ; curseur stable pendant l'évaluation | à vérifier |
| Page rechargée pendant une évaluation : la frise reprend sa progression | à vérifier |

## Vue du dossier

- **Fiche du lead** (en tête, hors impression) : `GET /api/contrats/{n}/souscripteur` (civilité, nom, prénom, adresse, mobile en lien `tel:`, e-mail en lien `mailto:`, véhicule). Exception à la minimisation décidée par Acerola le 27/10 : jamais envoyée au cluster ni à un LLM.
- **Lancer / Reprendre** : `POST /v1/souscriptions/{n}/evaluation` ; pendant l'appel, `GET /api/contrats/{n}/etat` chaque seconde (frise, temps écoulé, `trace_id`). Un second clic est ignoré tant que l'appel est en vol. Page rechargée pendant une évaluation (`EN_COURS`) : l'état se relit chaque seconde, deux minutes au plus. Une ré-évaluation n'affiche pas les étapes de la tentative précédente comme faites ; après « Reprendre », la pause ne compte pas dans les durées.
- **Pause** : `POST /v1/souscriptions/{n}/pause`, actif pendant l'évaluation ; elle s'arrête après l'agent en cours (statut `EN_PAUSE`). Réponse `{"pause": "ignoree"}` quand plus aucun agent ne reste à appeler : la page l'annonce (« Pause sans effet »).
- **Détail d'une étape** : mode, cause, durée, **tokens** (lus une fois dans la trace : attributs `gen_ai.usage.*` du span `invoke_agent` de l'agent ; « — (aucun appel LLM) » quand le total est nul), puis les spans de sa trace réduits à une liste blanche (outil MCP, décision, code ; agent, mode, cause) — jamais de prompt ni de sortie du modèle.
- **Pièces manquantes** (pastille quand la section `pieces` est `incomplet`) : mail prérempli et modifiable ; « Envoyer la relance » fait `POST /api/contrats/{n}/relances`, qui l'**enregistre et le trace comme envoyé, sans e-mail** avant ACS (#123, 15/11). Trois au plus (`409 RELANCES_EPUISEES`), jamais sur un dossier décidé (`409 DOSSIER_DECIDE`), seulement pour des pièces que l'agent Pièces a trouvées manquantes (`400 PIECES_INVALIDES`) ; deux envois simultanés : le second reçoit `409 RELANCE_CONCURRENTE` ; le span ne porte que le rang et les types de pièces, jamais le texte.
- **Contrat proposé** : fiche et prime des sections de l'état ; revue avec motif obligatoire (Valider, Corriger et accepter, Refuser). Après `ACCEPTE`, `GET /v1/souscriptions/{n}/contrat` : le contrat s'affiche dans une **visionneuse** (cadre de 70vh qui défile ; page à largeur A4, 794 px, qui défile horizontalement sur un écran étroit ; cadre focusable, `role="region"`, pour défiler au clavier), « Imprimer » hors du cadre (`@media print` neutralise le cadre et la largeur fixe, #145). Le contrat suit le modèle fictif d'Acerola : en-tête (n°, effet, échéance à un an moins un jour, reconduction tacite), 1. souscripteur, 2. véhicule, 3. garanties et franchises, 4. cotisation (TTC annuelle, prélèvement mensuel), 5. notice RGPD (articles 13, 14 et 22), puis conditions générales (notice du contrat type, lue au corpus) et références de la décision.
- **Après `REVUE_HUMAINE`, trois relances envoyées** : « Classer sans suite » (`POST /api/contrats/{n}/sans-suite`, statut `SANS_SUITE`, K8).
