using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Contrat généré d'un dossier accepté (#101).</summary>
public sealed class LireContratGenere(IDepotContratGenere depot)
{
    public Task<(ContratGenere? Contrat, bool Existe)> Executer(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        depot.LireContratGenere(gestionnaireId, numeroContrat, ct);
}
