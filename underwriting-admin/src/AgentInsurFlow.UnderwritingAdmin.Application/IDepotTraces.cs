using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port du référentiel SQL des traces : écriture (compte writer) et lecture (compte reader).</summary>
public interface IDepotTraces
{
    /// <summary>Insère les spans ; un span déjà connu (<c>trace_id</c>, <c>span_id</c>) est ignoré. Rend le nombre de nouveaux spans.</summary>
    Task<int> Inserer(IReadOnlyList<Span> spans, CancellationToken ct);

    /// <summary>Les spans d'une trace, dans l'ordre de leur début.</summary>
    Task<IReadOnlyList<Span>> Lire(string traceId, CancellationToken ct);
}
