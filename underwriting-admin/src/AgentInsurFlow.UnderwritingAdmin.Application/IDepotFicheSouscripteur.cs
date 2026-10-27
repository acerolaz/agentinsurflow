using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port de lecture de la fiche du lead, borné au gestionnaire (BOLA) : <c>null</c> = inexistant ou à un autre.</summary>
public interface IDepotFicheSouscripteur
{
    Task<FicheSouscripteur?> LireFiche(string gestionnaireId, string numeroContrat, CancellationToken ct);
}
