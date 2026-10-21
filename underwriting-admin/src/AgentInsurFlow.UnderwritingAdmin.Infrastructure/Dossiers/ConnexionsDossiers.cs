using Npgsql;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>
/// Connexions à la base <c>dossiers</c>, mêmes variables que <c>rag</c> (PG_HOST, PG_PORT, PG_SUFFIXE_BASES).
/// <c>migrateur</c> (propriétaire) ne sert qu'au démarrage ; les routes lisent avec <c>dossiers</c>.
/// </summary>
public sealed record ConnexionsDossiers(string Hote, int Port, string SuffixeBase, string? MotDePasseMigrateur, string MotDePasseDossiers)
{
    public string Migrateur => Chaine("migrateur", MotDePasseMigrateur
        ?? throw new InvalidOperationException("PG_MIGRATEUR_PASSWORD manquant"));

    public string Dossiers => Chaine("dossiers", MotDePasseDossiers);

    private string Chaine(string compte, string motDePasse) => new NpgsqlConnectionStringBuilder
    {
        Host = Hote,
        Port = Port,
        Database = $"dossiers{SuffixeBase}",
        Username = compte,
        Password = motDePasse,
    }.ConnectionString;
}
