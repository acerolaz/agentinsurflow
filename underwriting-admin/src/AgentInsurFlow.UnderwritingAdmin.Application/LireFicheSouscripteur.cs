using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Fiche du lead (coordonnées et véhicule) pour le détail du dossier.</summary>
public sealed class LireFicheSouscripteur(IDepotFicheSouscripteur depot)
{
    public Task<FicheSouscripteur?> Executer(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        depot.LireFiche(gestionnaireId, numeroContrat, ct);
}
