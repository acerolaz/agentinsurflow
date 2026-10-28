using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise;

/// <summary>Contexte pour <c>dotnet ef migrations add</c> (hors exécution) : aucune base n'est jointe pour générer.</summary>
internal sealed class PointsDeRepriseDbContextFactory : IDesignTimeDbContextFactory<PointsDeRepriseDbContext>
{
    public PointsDeRepriseDbContext CreateDbContext(string[] args) =>
        Creer(new ConnexionsPointsDeReprise("localhost", 5432, "", "design", "design").Migrateur);

    /// <summary>Un contexte sur la chaîne donnée, avec les noms en snake_case (tables et colonnes PostgreSQL).</summary>
    internal static PointsDeRepriseDbContext Creer(string chaine) =>
        new(new DbContextOptionsBuilder<PointsDeRepriseDbContext>()
            .UseNpgsql(chaine, o => o.MigrationsHistoryTable("__EFMigrationsHistory", PointsDeRepriseDbContext.Schema)) // celui de public est l'historique des dossiers
            .UseSnakeCaseNamingConvention().Options);
}
