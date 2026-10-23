using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port de lecture des dossiers : toujours borné au gestionnaire (BOLA), sur la vue minimisée.</summary>
public interface IDepotDossiers
{
    Task<IReadOnlyList<VueContrat>> Lister(string gestionnaireId, int limit, int offset, CancellationToken ct);

    /// <summary>Rend <c>null</c> si le contrat n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<VueContrat?> Trouver(string gestionnaireId, string numeroContrat, CancellationToken ct);

    /// <summary>Pièces déclarées du contrat ; <c>null</c> si le contrat n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<IReadOnlyList<PieceDeclaree>?> ListerPieces(string gestionnaireId, string numeroContrat, CancellationToken ct);
}
