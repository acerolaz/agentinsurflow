using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Pièces déclarées d'un contrat du gestionnaire ; <c>null</c> aussi pour le contrat d'un autre (même réponse que « inexistant »).</summary>
public sealed class ListerPieces(IDepotDossiers depot)
{
    public Task<IReadOnlyList<PieceDeclaree>?> Executer(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        depot.ListerPieces(gestionnaireId, numeroContrat, ct);
}
