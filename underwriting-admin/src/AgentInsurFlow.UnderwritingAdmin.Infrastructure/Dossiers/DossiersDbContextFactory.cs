using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>Contexte pour <c>dotnet ef migrations add</c> (hors exécution) : aucune base n'est jointe pour générer.</summary>
internal sealed class DossiersDbContextFactory : IDesignTimeDbContextFactory<DossiersDbContext>
{
    public DossiersDbContext CreateDbContext(string[] args) =>
        Creer(new ConnexionsDossiers("localhost", 5432, "", "design", "design").Migrateur);

    /// <summary>Un contexte sur la chaîne donnée, avec les noms en snake_case (tables et colonnes PostgreSQL).</summary>
    internal static DossiersDbContext Creer(string chaine) => new(Options(chaine));

    internal static DbContextOptions<DossiersDbContext> Options(string chaine) =>
        new DbContextOptionsBuilder<DossiersDbContext>().UseNpgsql(chaine).UseSnakeCaseNamingConvention().Options;
}
