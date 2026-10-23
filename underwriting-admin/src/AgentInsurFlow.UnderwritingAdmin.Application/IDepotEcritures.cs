using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port d'écriture des dossiers : toujours borné au gestionnaire (BOLA).</summary>
public interface IDepotEcritures
{
    /// <summary><c>false</c> si le contrat n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
        PrimeBrouillon? prime, CancellationToken ct);

    /// <summary>
    /// <c>Ecrit=false, CodeRefus=null</c> si le contrat n'existe pas ou appartient à un autre gestionnaire ;
    /// <c>DECISION_ABSENTE</c> si une validation est demandée sans décision brouillon (rien n'est écrit).
    /// L'auteur de la validation est le gestionnaire.
    /// </summary>
    Task<ResultatEcriture> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
        CancellationToken ct);

    /// <summary>Statut courant du contrat ; <c>null</c> s'il n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<string?> StatutContrat(string gestionnaireId, string numeroContrat, CancellationToken ct);

    /// <summary>Écrase les observations ; <c>false</c> si le contrat n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<bool> EnregistrerObservations(string gestionnaireId, string numeroContrat, string observations, CancellationToken ct);

    /// <summary>
    /// Mémoire long terme du dossier (D100), idempotente : état et sections en upsert, rapports et tours en insertion qui
    /// ignore un doublon. <c>false</c> si le contrat n'existe pas ou appartient à un autre gestionnaire (rien n'est écrit).
    /// </summary>
    Task<bool> EnregistrerEtat(string gestionnaireId, string numeroContrat, EtatEntrant etat, CancellationToken ct);
}

/// <summary><c>Ecrit=false, CodeRefus=null</c> : contrat introuvable (404).</summary>
public sealed record ResultatEcriture(bool Ecrit, string? CodeRefus);
