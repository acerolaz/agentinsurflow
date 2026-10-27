namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Port des relances de pièces manquantes (#130), borné au gestionnaire (BOLA). Aucun e-mail n'est envoyé (ACS : #123).</summary>
public interface IDepotRelances
{
    /// <summary>Relances déjà enregistrées ; <c>null</c> si le contrat n'existe pas ou appartient à un autre gestionnaire.</summary>
    Task<int?> NbRelances(string gestionnaireId, string numeroContrat, CancellationToken ct);

    /// <summary>Enregistre la relance (auteur = gestionnaire) et rend son rang ; met à jour le compteur de l'état s'il existe.</summary>
    Task<int> Ajouter(string gestionnaireId, string numeroContrat, string texte, IReadOnlyList<string> pieces, CancellationToken ct);
}

/// <summary><c>Rang=null, CodeRefus=null</c> : contrat introuvable (404).</summary>
public sealed record ResultatRelance(int? Rang, string? CodeRefus);
