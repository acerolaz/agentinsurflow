using AgentInsurFlow.UnderwritingAdmin.Application;
using Microsoft.Extensions.DependencyInjection;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Traces;

public static class TracesServices
{
    /// <summary>Câble le port <see cref="IDepotTraces"/> sur la base <c>traces</c>.</summary>
    public static IServiceCollection AjouterTraces(this IServiceCollection services, ConnexionsTraces connexions)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(connexions);
        return services.AddSingleton<IDepotTraces>(new DepotTracesEf(connexions));
    }
}
