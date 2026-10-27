using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port des relances de pièces manquantes (#130), borné au gestionnaire (BOLA). Aucun e-mail n'est envoyé (ACS : #123).</summary>
public interface IDepotRelances
{
    /// <summary>Situation du dossier pour une relance ; <c>null</c> si le contrat n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<SituationRelance?> Situation(string gestionnaireId, string numeroContrat, CancellationToken ct);

    /// <summary>
    /// Enregistre la relance (auteur = gestionnaire) et rend son rang ; met à jour le compteur de l'état s'il existe.
    /// <c>null</c> : un envoi simultané a pris ce rang (clé <c>(numero_contrat, rang)</c>), rien n'est écrit.
    /// </summary>
    Task<int?> Ajouter(string gestionnaireId, string numeroContrat, string texte, IReadOnlyList<string> pieces, CancellationToken ct);

    /// <summary>
    /// Classe le dossier <c>SANS_SUITE</c> (statut du contrat et de l'état) ; <c>false</c> : il a été figé entre-temps, rien n'est écrit.
    /// </summary>
    Task<bool> ClasserSansSuite(string gestionnaireId, string numeroContrat, CancellationToken ct);
}

/// <summary><c>Rang=null, CodeRefus=null</c> : contrat introuvable (404).</summary>
public sealed record ResultatRelance(int? Rang, string? CodeRefus);
