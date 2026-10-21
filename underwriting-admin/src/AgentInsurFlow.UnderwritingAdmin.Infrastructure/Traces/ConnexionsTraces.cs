using Npgsql;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Traces;

/// <summary>
/// Connexions à la base <c>traces</c> : <c>migrateur</c> (propriétaire) au démarrage, <c>traces_writer</c> pour écrire
/// les spans, <c>traces_reader</c> pour les relire. Chaque compte n'a que le droit dont il se sert.
/// </summary>
public sealed record ConnexionsTraces(
    string Hote, int Port, string SuffixeBase, string? MotDePasseMigrateur, string MotDePasseWriter, string MotDePasseReader)
{
    public string Migrateur => Chaine("migrateur", MotDePasseMigrateur
        ?? throw new InvalidOperationException("PG_MIGRATEUR_PASSWORD manquant"));

    public string Writer => Chaine("traces_writer", MotDePasseWriter);

    public string Reader => Chaine("traces_reader", MotDePasseReader);

    private string Chaine(string compte, string motDePasse) => new NpgsqlConnectionStringBuilder
    {
        Host = Hote,
        Port = Port,
        Database = $"traces{SuffixeBase}",
        Username = compte,
        Password = motDePasse,
    }.ConnectionString;
}
