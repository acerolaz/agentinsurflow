using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Traces;

/// <summary>Migrations de la base <c>traces</c> au démarrage, avec le compte <c>migrateur</c>.</summary>
public static class MigrationsTraces
{
    /// <summary>Attend PostgreSQL (au plus <paramref name="attenteMax"/>), puis applique les migrations en attente.</summary>
    public static async Task AppliquerAsync(ConnexionsTraces connexions, TimeSpan attenteMax, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(connexions);
        await using var db = TracesDbContextFactory.Creer(connexions.Migrateur);
        var limite = DateTime.UtcNow + attenteMax;
        while (!await db.Database.CanConnectAsync(ct))
        {
            if (DateTime.UtcNow >= limite)
            {
                throw new TimeoutException($"PostgreSQL injoignable après {attenteMax.TotalSeconds:0} s");
            }
            await Task.Delay(TimeSpan.FromSeconds(1), ct);
        }
        await db.Database.MigrateAsync(ct);
    }
}
