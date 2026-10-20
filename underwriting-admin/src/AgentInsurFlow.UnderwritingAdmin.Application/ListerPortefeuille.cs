using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Les contrats du gestionnaire, paginés ; <c>limit</c> est borné pour qu'aucune requête n'aspire tout le portefeuille.</summary>
public sealed class ListerPortefeuille(IDepotDossiers depot)
{
    public const int LimiteMax = 100;

    public Task<IReadOnlyList<VueContrat>> Executer(string gestionnaireId, int limit, int offset, CancellationToken ct) =>
        depot.Lister(gestionnaireId, Math.Clamp(limit, 1, LimiteMax), Math.Max(offset, 0), ct);
}
