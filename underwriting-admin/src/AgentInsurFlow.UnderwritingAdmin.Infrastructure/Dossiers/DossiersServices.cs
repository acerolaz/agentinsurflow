using AgentInsurFlow.UnderwritingAdmin.Application;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

public static class DossiersServices
{
    /// <summary>Câble le port <see cref="IDepotDossiers"/> sur la vue, avec le compte <c>dossiers</c> (lecture par la vue) et le port <see cref="IDepotEcritures"/> (écritures bornées par les droits SQL).</summary>
    public static IServiceCollection AjouterDossiers(this IServiceCollection services, ConnexionsDossiers connexions)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(connexions);
        services.AddDbContext<DossiersDbContext>(o => o.UseNpgsql(connexions.Dossiers).UseSnakeCaseNamingConvention());
        services.AddScoped<IDepotEcritures, DepotEcrituresEf>();
        services.AddScoped<IDepotRelances, DepotEcrituresEf>();
        services.AddScoped<IDepotEtat, DepotDossiersEf>();
        services.AddScoped<IDepotContratGenere, DepotDossiersEf>();
        services.AddScoped<IDepotFicheSouscripteur, DepotDossiersEf>();
        return services.AddScoped<IDepotDossiers, DepotDossiersEf>();
    }
}
