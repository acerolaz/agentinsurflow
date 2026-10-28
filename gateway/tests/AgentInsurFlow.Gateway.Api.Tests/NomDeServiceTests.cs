using Microsoft.Extensions.DependencyInjection;
using OpenTelemetry;
using OpenTelemetry.Trace;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>Variables d'environnement du processus : ces tests ne tournent jamais en parallèle des autres.</summary>
[CollectionDefinition(nameof(VariablesEnvironnement), DisableParallelization = true)]
public sealed class VariablesEnvironnement;

/// <summary>
/// En Container Apps, le détecteur de ressource d'Azure Monitor pose service.name = nom de l'app (CONTAINER_APP_NAME) :
/// la gateway doit garder le sien, que l'E2E et le référentiel des traces cherchent (#158).
/// </summary>
[Collection(nameof(VariablesEnvironnement))]
public sealed class NomDeServiceTests(Backends backends) : IClassFixture<Backends>
{
    [Fact]
    public void Sous_container_apps_le_nom_de_service_reste_celui_de_la_gateway()
    {
        Environment.SetEnvironmentVariable("CONTAINER_APP_NAME", "insurflow-test");
        try
        {
            using var usine = backends.Gateway([("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000-0000-0000-000000000000")]);
            var ressource = usine.Services.GetRequiredService<TracerProvider>().GetResource();

            Assert.Equal("agentinsurflow-gateway", ressource.Attributes.Single(a => a.Key == "service.name").Value);
        }
        finally
        {
            Environment.SetEnvironmentVariable("CONTAINER_APP_NAME", null);
        }
    }
}
