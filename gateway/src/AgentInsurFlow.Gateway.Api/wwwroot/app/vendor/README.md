# Dépendances tierces de l'espace gestionnaire

Copiées telles quelles depuis le registre npm, sans npm dans le dépôt ; la CSP (`script-src 'self'`) interdit tout CDN.

| Fichier | Paquet | Version | Publiée le | SHA-384 (attribut `integrity`) |
|---|---|---|---|---|
| `msal-browser.min.js` | `@azure/msal-browser` (`lib/msal-browser.min.js`, UMD, global `msal`) | 4.30.0 (dist-tag `lts`) | 2026-03-18 | `sha384-RGxxfG5yRS8DLU7ZJ8OoLhbV/BsJFHyPuMVHrTLbpj3t5Z15LnviJmaznKY/a7LZ` |

- Tarball vérifié contre `dist.integrity` du registre (`sha512-HBBKfbZk…OLxR+w==`). Licence MIT : `LICENSE-msal-browser`.
- 4.30.0 plutôt que 5.x : la v5 (6 jours au moment du choix) change le traitement des réponses popup et iframe (pont de redirection) ; la ligne `lts` suffit au flux redirection + jeton silencieux.

Mise à jour : `npm pack @azure/msal-browser@<version>` hors du dépôt, vérifier l'empreinte du tarball, copier `package/lib/msal-browser.min.js`, puis recalculer
`openssl dgst -sha384 -binary msal-browser.min.js | openssl base64 -A` et reporter la valeur ici et dans `../index.html`.
