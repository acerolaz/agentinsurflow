using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port de lecture du contrat généré (#101), borné au gestionnaire (BOLA).</summary>
public interface IDepotContratGenere
{
    /// <summary><c>Existe=false</c> : inexistant ou à un autre gestionnaire ; <c>Contrat=null</c> : statut différent d'ACCEPTE.</summary>
    Task<(ContratGenere? Contrat, bool Existe)> LireContratGenere(string gestionnaireId, string numeroContrat, CancellationToken ct);
}
