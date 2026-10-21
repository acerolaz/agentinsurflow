namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>
/// Un span OpenTelemetry, colonnes de la table <c>span</c> (spec §9.3). Les attributs, événements et liens
/// sont du JSON déjà sérialisé : le référentiel les garde tels que reçus (jamais de donnée personnelle ajoutée ici).
/// </summary>
public sealed record Span(
    string TraceId,
    string SpanId,
    string? ParentSpanId,
    string TraceState,
    string Name,
    int Kind,
    long StartTimeUnixNano,
    long EndTimeUnixNano,
    int StatusCode,
    string StatusMessage,
    string ServiceName,
    string ResourceAttributes,
    string Attributes,
    string ScopeName,
    string ScopeVersion,
    string Events,
    string Links,
    DateTimeOffset RecuLe)
{
    /// <summary>Durée en millisecondes, comme la colonne générée <c>duree_ms</c>.</summary>
    public double DureeMs => (EndTimeUnixNano - StartTimeUnixNano) / 1e6;
}
