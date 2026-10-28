# Amendement au dossier de conception (V1.2) — point ouvert P45

**P45 : reporter dans L5 et L11 les écarts du §10.1** de l'addendum V2.13 (p. 53). Le dossier décrit la cible d'origine ; le code en production (v0.6.0, 22/10) s'en écarte sur trois points, que le §10.1 consigne déjà :

- la gateway est en **.NET 10** (« dossier : .NET 8 ») ;
- `underwriting-admin` est en **C#, Clean Architecture** (« dossier : "Service Dossiers" FastAPI ») ;
- la CI/CD et le suivi sont sur **GitHub Actions** et le tableau GitHub (« dossier : Gitea / Kanboard, D43 »).

Source : `dossier-conception-v1.2.pdf` (hors dépôt), texte extrait avec pypdf le 28/10. Les numéros de page sont ceux du PDF. L'extraction perd certains symboles (flèches, parenthèses, « + ») : les textes actuels sont cités tels que l'extraction les rend, sans les reconstituer. Le P45 de la p. 55 est lui-même cité : « Reporter dans L5 / L11 les écarts du §10.1 .NET 10, underwriting-admin en C#, GitHub Actions) — Acerola ».

| Section | Texte actuel | Texte corrigé |
|---|---|---|
| p. 24, L5 §5.1, ligne « Point de passage unique » | « ASP.NET Core 8  YARP » (suivi de « Routage externe et interne, validation des jetons, allow-list, rate limiting, traceparent ») | « ASP.NET Core 10 · YARP » (écart : .NET 10, §10.1) |
| p. 24, L5 §5.1, ligne « Services de données » | « 2 services FastAPI : Service RAG (ingestion + recherche) · Service Dossiers (base SQL  Blob) » | « 2 services : Service RAG (Python, FastAPI, hexagonal ; ingestion + recherche) · underwriting-admin (C#, Clean Architecture ; dossiers et référentiel des traces) » (écart : underwriting-admin en C#, §10.1) |
| p. 24, L5 §5.1, ligne « CI/CD » | « Gitea Actions · Terraform · Trunk-Based Development » | « GitHub Actions · Terraform · Trunk-Based Development » (écart : GitHub Actions, §10.1) |
| p. 24, L5 §5.1, ligne « Suivi » | « Kanboard (lien public en lecture) » | « Tableau GitHub AgentInsurFlow (projet n° 1) » (écart : GitHub, §10.1 ; source citée p. 53) |
| p. 24, L5 §5.2 « L'élément exotique : la gateway C# », phrase d'introduction | « Le socle dʼun projet « Développeur en IA » est Python ; la gateway en C# / ASP.NET Core 8 est la seule dérogation. » | « Le socle dʼun projet « Développeur en IA » est Python ; les services C# (la gateway en ASP.NET Core 10 et underwriting-admin) sont les seules dérogations. » |
| p. 25, L5 §5.2, tableau des arguments, ligne « Coût » | « Un 2ᵉ runtime (.NET dans la CI » (extraction coupée ; fin de ligne à vérifier dans le PDF) | « Un 2ᵉ runtime (.NET 10 dans la CI … » (suite du texte : à vérifier dans le PDF) |
| p. 37, L11 §11.1, ligne « Outillage de suivi », option B | « Gitea  Kanboard — ➖  écart avec la cible GitHub Actions » (décision B, D43) | « Gitea + Kanboard (décision B, D43), remplacés en production par GitHub Actions et le tableau GitHub : l'écart avec la cible est levé (§10.1) » |
| p. 37, L11 §11.2, ligne « Industrialisation §5 » | « Esquisse adaptée au MVP  Gitea, promotion directe sans canary ; implémentation en V2 D56, D57 » | « Esquisse adaptée au MVP GitHub Actions, promotion directe sans canary ; chaîne bloquante jusqu'à la production déjà en place (§10.1) ; LLMOps en V2 D56, D57 » |
| p. 37, L11 §11.2, ligne « Gitea et code existant » | « .xlsx Gitea  Kanboard ; existant réutilisé D35, D43 » (en-tête de ligne : « Gitea et code existant ») | « .xlsx GitHub Actions et tableau GitHub ; existant réutilisé D35, D43 » (écart : GitHub, §10.1) |

Hors périmètre de P45, à reporter ailleurs (L2, L6, L7) : la même ancienne pile apparaît p. 6 (« Service Dossiers », « CI Gitea Actions »), p. 25 (schéma L6 : « Gateway C#  ASP.NET Core 8  YARP », « Service Dossiers FastAPI ») et p. 31 (L7 : « Gitea Actions »).

Regrouper cet amendement avec ceux de D106 et D42 : voir [`amendements.md`](amendements.md).
