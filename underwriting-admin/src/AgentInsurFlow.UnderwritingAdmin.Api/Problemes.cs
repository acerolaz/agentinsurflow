namespace AgentInsurFlow.UnderwritingAdmin.Api;

/// <summary>Erreurs au format ProblemDetails (RFC 9457) avec un champ <c>code</c>, comme la gateway et rag.</summary>
internal static class Problemes
{
    public static IResult Creer(int statut, string titre, string code) =>
        Results.Problem(statusCode: statut, title: titre, extensions: new Dictionary<string, object?> { ["code"] = code });
}
