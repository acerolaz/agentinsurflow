# Espace gestionnaire

Page HTML + JavaScript sans étape de build, servie par la gateway sous **`/app/`** (Swagger garde la racine). Spec : [`superpowers/specs/2026-10-27-espace-gestionnaire-design.md`](superpowers/specs/2026-10-27-espace-gestionnaire-design.md) ; issues #103, #104, #101, #129, #130.

## Fichiers

| Fichier (`gateway/src/AgentInsurFlow.Gateway.Api/wwwroot/app/`) | Rôle |
|---|---|
| `index.html`, `app.css` | Coquille, deux thèmes par variables (`data-theme` sur `<html>`) |
| `app.js` | Routeur sur le fragment (`#/dossiers`, `#/dossiers/AIF-…`, `#/tchat`), en-tête à onglets, portefeuille, tchat |
| `dossier.js` | Vue d'un dossier (#104) |
| `auth.js` | MSAL en redirection (code + PKCE, client public) ; le choix A/B ne fait que préremplir `loginHint` |
| `api.js` | Appels à la gateway avec le jeton du service ; un 401 est réessayé une fois avec un jeton renouvelé |
| `dom.js`, `logique.js` | Rendu sans `innerHTML` ; logique pure testée par `make espace-test` |
| `vendor/` | `msal-browser` versionné (version et SHA-384 dans `vendor/README.md`) |

Configuration publique, sans secret : `GET /app/config.json`, lue dans la section `Espace` de la gateway (`Espace__ClientId` à défaut `SWAGGER_CLIENT_ID`, `Espace__Authority`, `Espace__Scopes__Rag|Underwriting|Cluster`, `Espace__Comptes__A|B`).

## Sécurité

- CSP servie avec chaque fichier : `script-src 'self'`, `style-src 'self'`, `connect-src 'self' https://login.microsoftonline.com`, `frame-ancestors 'none'`. Aucun CDN ; `integrity` SRI sur MSAL (un TI vérifie qu'il correspond au fichier servi).
- Les jetons restent en `sessionStorage` (MSAL) ; chaque service revalide le jeton, la page n'est qu'un client.
- Tout texte venu d'un service est inséré par `textContent` ; un numéro de dossier hors `^AIF-\d{4}-\d{6}$` ne s'ouvre pas.

## Accessibilité (RGAA 11.1 / WCAG 2.1.1)

Prévu dans le code :
- onglets `role="tablist"`, passage aux flèches gauche/droite, `aria-selected` ;
- bouton de thème avec `aria-pressed` ; focus visible (`:focus-visible`) dans les deux thèmes ;
- connexion par `<input type="radio">` étiquetés dans un `fieldset` ;
- portefeuille : chaque numéro est un lien (Entrée l'ouvre) ;
- fil du tchat en `aria-live="polite"`, erreurs en `role="alert"`.

**Vérification au clavier seul** (à faire en local, `make up`, `http://localhost:8000/app/`) — *non faite par Claude : la connexion Entra est interactive.*

| Parcours | Résultat |
|---|---|
| Connexion A | à vérifier |
| Onglets aux flèches | à vérifier |
| Ouverture d'un dossier avec Entrée | à vérifier |
| Thème basculé puis gardé après rechargement | à vérifier |
| Question au tchat : réponse et sources | à vérifier |
