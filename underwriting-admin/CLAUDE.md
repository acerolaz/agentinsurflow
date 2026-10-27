# underwriting-admin — règles du projet

Dossiers minimisés (BOLA) et référentiel SQL des traces OTLP. Contrat transverse : [`../CLAUDE.md`](../CLAUDE.md) ;
architecture : `~/.claude/rules/csharp-clean-architecture.md` ; tests : [`../.claude/rules/testing-pyramid.md`](../.claude/rules/testing-pyramid.md).

## Non-négociables

- `Domain` sans aucune référence NuGet ; `Application` ne connaît que des ports ; les tests de dépendance le vérifient.
- Les routes lisent les dossiers **uniquement par `vue_contrat_minimisee`** avec le compte `dossiers` ; jamais de nom, d'adresse ni de numéro de permis dans une réponse ou un span.
  **Seule exception (décision d'Acerola, 27/10)** : `GET …/contrat` (contrat imprimé) lit les parties au contrat par `vue_contrat_accepte` (contrats `ACCEPTE` du gestionnaire seulement, ni e-mail ni téléphone) ; jamais dans un span ni une trace, jamais vers le cluster ni un LLM. La table `souscripteur` reste fermée au compte `dossiers` (test `Compte_dossiers_ne_lit_ni_souscripteur…`).
- **BOLA** : `gestionnaire_id` vient du claim `oid`, jamais d'un paramètre ; contrat d'un autre gestionnaire = même 404 qu'un contrat inexistant.
- JSON en **snake_case** (les clés que lit `rag`) ; erreurs en ProblemDetails avec `code`.
- `/v1/traces` sans jeton seulement depuis `Otlp:SourcesSansJeton` sans `X-Forwarded-For` ; jamais élargir le défaut en Azure.
- SQL toujours paramétré ; migrations EF Core seulement (vue, droits et seed par `migrationBuilder.Sql`).
- .NET 10 : `PATH="$HOME/.dotnet:$PATH"` si le `dotnet` du système est plus ancien.
