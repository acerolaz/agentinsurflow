# gateway — règles du projet

YARP, seule entrée publique. Contrat transverse : [`../CLAUDE.md`](../CLAUDE.md) ;
architecture : `~/.claude/rules/csharp-clean-architecture.md` (un seul projet `Api` : proxy pur, pas de couche artificielle) ;
tests : forme « diamant » ([`../.claude/rules/testing-pyramid.md`](../.claude/rules/testing-pyramid.md)).

## Non-négociables

- **Refus par défaut** : chaque route d'`appsettings.Routes.json` déclare son `AuthorizationPolicy` (rôle **et** audience du service visé).
- Les services revalident toujours le jeton : la gateway n'est pas la seule défense.
- `X-Forwarded-For` toujours réécrit ; l'IP réelle n'est reprise de l'envoy que si `Proxy__EnvoyDevant=true` (Azure).
- Erreurs en ProblemDetails : `NON_AUTHENTIFIE` (401), `ACCES_REFUSE` (403), `TROP_DE_REQUETES` (429).
- Documentation ouverte seulement en `GET` sur les documents OpenAPI des services ; jamais de route vers un service inexistant.
