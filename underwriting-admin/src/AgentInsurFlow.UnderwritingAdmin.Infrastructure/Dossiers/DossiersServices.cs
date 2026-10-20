using AgentInsurFlow.UnderwritingAdmin.Application;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

public static class DossiersServices
{
    /// <summary>Câble le port <see cref="IDepotDossiers"/> sur la vue, avec le compte <c>dossiers</c> (lecture seule).</summary>
    public static IServiceCollection AjouterDossiers(this IServiceCollection services, ConnexionsDossiers connexions)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(connexions);
        services.AddDbContext<DossiersDbContext>(o => o.UseNpgsql(connexions.Dossiers).UseSnakeCaseNamingConvention());
        return services.AddScoped<IDepotDossiers, DepotDossiersEf>();
    }
}
