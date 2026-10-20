using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Traces;

/// <summary>Contexte pour <c>dotnet ef migrations add</c> (hors exécution) : aucune base n'est jointe pour générer.</summary>
internal sealed class TracesDbContextFactory : IDesignTimeDbContextFactory<TracesDbContext>
{
    public TracesDbContext CreateDbContext(string[] args) =>
        Creer(new ConnexionsTraces("localhost", 5432, "", "design", "design", "design").Migrateur);

    /// <summary>Un contexte sur la chaîne donnée, avec les noms en snake_case (tables et colonnes PostgreSQL).</summary>
    internal static TracesDbContext Creer(string chaine) =>
        new(new DbContextOptionsBuilder<TracesDbContext>().UseNpgsql(chaine).UseSnakeCaseNamingConvention().Options);
}
