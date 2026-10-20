using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Enregistre les spans reçus ; rejouer la même requête n'ajoute rien (idempotent).</summary>
public sealed class EnregistrerSpans(IDepotTraces depot)
{
    public Task<int> Executer(IReadOnlyList<Span> spans, CancellationToken ct) =>
        spans.Count == 0 ? Task.FromResult(0) : depot.Inserer(spans, ct);
}
