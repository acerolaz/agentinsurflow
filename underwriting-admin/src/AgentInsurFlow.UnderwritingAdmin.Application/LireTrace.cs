using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Les spans d'une trace ; liste vide si la trace est inconnue.</summary>
public sealed class LireTrace(IDepotTraces depot)
{
    public Task<IReadOnlyList<Span>> Executer(string traceId, CancellationToken ct) => depot.Lire(traceId, ct);
}
