using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Un contrat du gestionnaire ; <c>null</c> aussi pour le contrat d'un autre (même réponse que « inexistant »).</summary>
public sealed class ConsulterContrat(IDepotDossiers depot)
{
    public Task<VueContrat?> Executer(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        depot.Trouver(gestionnaireId, numeroContrat, ct);
}
