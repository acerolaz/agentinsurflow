using Microsoft.Extensions.DependencyInjection;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise;

public static class PointsDeRepriseServices
{
    /// <summary>Câble <see cref="IDepotPointsDeReprise"/> sur le schéma <c>points_reprise</c>.</summary>
    public static IServiceCollection AjouterPointsDeReprise(this IServiceCollection services, ConnexionsPointsDeReprise connexions)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(connexions);
        return services.AddSingleton<IDepotPointsDeReprise>(new DepotPointsDeRepriseEf(connexions));
    }
}
