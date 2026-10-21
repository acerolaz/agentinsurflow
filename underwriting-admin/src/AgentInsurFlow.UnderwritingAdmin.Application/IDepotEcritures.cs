using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port d'écriture des dossiers : toujours borné au gestionnaire (BOLA).</summary>
public interface IDepotEcritures
{
    /// <summary><c>false</c> si le contrat n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
        PrimeBrouillon? prime, CancellationToken ct);

    /// <summary><c>false</c> si le contrat n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<bool> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
        string auteur, CancellationToken ct);
}

/// <summary><c>Ecrit=false, CodeRefus=null</c> : contrat introuvable (404).</summary>
public sealed record ResultatEcriture(bool Ecrit, string? CodeRefus);
