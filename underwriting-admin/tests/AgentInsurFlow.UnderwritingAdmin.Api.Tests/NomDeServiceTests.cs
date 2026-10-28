using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;
using OpenTelemetry;
using OpenTelemetry.Trace;

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>Variables d'environnement du processus : ces tests ne tournent jamais en parallèle des autres.</summary>
[CollectionDefinition(nameof(VariablesEnvironnement), DisableParallelization = true)]
public sealed class VariablesEnvironnement;

/// <summary>
/// En Container Apps, le détecteur de ressource d'Azure Monitor pose service.name = nom de l'app (CONTAINER_APP_NAME) :
/// le service doit garder le sien, que l'E2E et le référentiel des traces cherchent (#158).
/// </summary>
[Collection(nameof(VariablesEnvironnement))]
public sealed class NomDeServiceTests
{
    [Fact]
    public void Sous_container_apps_le_nom_de_service_reste_celui_d_underwriting()
    {
        Environment.SetEnvironmentVariable("CONTAINER_APP_NAME", "insurflow-uw-test");
        try
        {
            using var usine = JetonsDeTest.Usine(b =>
                b.UseSetting("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000-0000-0000-000000000000"));
            var ressource = usine.Services.GetRequiredService<TracerProvider>().GetResource();

            Assert.Equal("agentinsurflow-underwriting", ressource.Attributes.Single(a => a.Key == "service.name").Value);
        }
        finally
        {
            Environment.SetEnvironmentVariable("CONTAINER_APP_NAME", null);
        }
    }
}
