using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port de lecture de la mémoire du dossier (D100), borné au gestionnaire (BOLA).</summary>
public interface IDepotEtat
{
    /// <summary>
    /// État de la tentative courante, rapports triés par création ; <c>null</c> si le contrat n'existe pas ou appartient à un
    /// autre gestionnaire. Toutes les sections sont rendues : le filtrage revient au cas d'usage.
    /// </summary>
    Task<EtatLu?> LireEtat(string gestionnaireId, string numeroContrat, CancellationToken ct);
}
