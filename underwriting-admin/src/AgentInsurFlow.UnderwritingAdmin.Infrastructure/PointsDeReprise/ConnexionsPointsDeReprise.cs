using Npgsql;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise;

/// <summary>
/// Connexions à la base <c>dossiers</c> pour le schéma <c>points_reprise</c> : <c>migrateur</c> (propriétaire) au démarrage,
/// <c>points_reprise</c> pour lire et écrire les points (aucun droit hors de son schéma).
/// </summary>
public sealed record ConnexionsPointsDeReprise(
    string Hote, int Port, string SuffixeBase, string? MotDePasseMigrateur, string MotDePassePointsDeReprise)
{
    public string Migrateur => Chaine("migrateur", MotDePasseMigrateur
        ?? throw new InvalidOperationException("PG_MIGRATEUR_PASSWORD manquant"));

    public string PointsDeReprise => Chaine("points_reprise", MotDePassePointsDeReprise);

    private string Chaine(string compte, string motDePasse) => new NpgsqlConnectionStringBuilder
    {
        Host = Hote,
        Port = Port,
        Database = $"dossiers{SuffixeBase}",
        Username = compte,
        Password = motDePasse,
    }.ConnectionString;
}
