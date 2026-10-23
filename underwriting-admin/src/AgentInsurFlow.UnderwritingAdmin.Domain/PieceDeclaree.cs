namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>
/// Pièce déclarée d'un contrat (métadonnées seulement) : jamais le nom de fichier, l'URL du blob ni l'auteur de la déclaration.
/// Noms JSON snake_case : <c>type</c>, <c>date_emission</c> (lus par l'agent Pièces du cluster).
/// </summary>
public sealed record PieceDeclaree(string Type, DateOnly DateEmission);

/// <summary>Liste fermée des types de pièces déclarables.</summary>
public static class TypesPiece
{
    public const string ReleveInformation = "releve_information";
    public const string Permis = "permis";

}
