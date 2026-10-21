using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// TI de l'IP réelle du client (S3-26, issue #10). En Azure, l'envoy de Container Apps ajoute l'IP du client
/// à la fin de <c>X-Forwarded-For</c> ; <c>Proxy:EnvoyDevant=true</c> la reprend (dernière entrée seulement).
/// Sans le drapeau (local), l'<c>X-Forwarded-For</c> du client est ignoré (voir RoutageTests).
/// </summary>
public sealed class IpClientTests(Backends backends) : IClassFixture<Backends>
{
    private static async Task<HttpResponseMessage> Envoyer(HttpClient client, string chemin, string xff, string? jeton = null)
    {
        using var requete = Requete("GET", chemin, jeton);
        requete.Headers.Add("X-Forwarded-For", xff);
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    [Fact]
    public async Task EnvoyDevant_IP_reelle_transmise()
    {
        using var usine = backends.Gateway(("Proxy:EnvoyDevant", "true"));
        using var client = usine.CreateClient();

        await Envoyer(client, "/api/contrats", "10.0.0.1, 203.0.113.7", Creer(AudienceUnderwriting, ["Gestionnaire"]));

        var entetes = Assert.Single(backends.Underwriting.LogEntries).RequestMessage!.Headers!;
        Assert.Equal("203.0.113.7", string.Join(",", entetes["X-Forwarded-For"]));
    }

    [Fact]
    public async Task EnvoyDevant_IP_reelle_dans_le_span()
    {
        var adresses = new ConcurrentBag<string?>();
        using var ecoute = new ActivityListener
        {
            ShouldListenTo = s => s.Name == "Microsoft.AspNetCore",
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = a => adresses.Add(a.GetTagItem("client.address") as string),
        };
        ActivitySource.AddActivityListener(ecoute);
        using var usine = backends.Gateway(("Proxy:EnvoyDevant", "true"));
        using var client = usine.CreateClient();

        await Envoyer(client, "/rag/openapi.json", "10.0.0.1, 203.0.113.42");

        Assert.Contains("203.0.113.42", adresses);
    }

    [Fact]
    public async Task EnvoyDevant_partitionne_par_IP_reelle()
    {
        using var usine = backends.Gateway(("Proxy:EnvoyDevant", "true"), ("RateLimit:Global:PermitLimit", "1"));
        using var client = usine.CreateClient();

        var a = await Envoyer(client, "/rag/openapi.json", "203.0.113.7");
        var b = await Envoyer(client, "/rag/openapi.json", "203.0.113.8");
        var encoreA = await Envoyer(client, "/rag/openapi.json", "198.51.100.1, 203.0.113.7");

        Assert.Equal(HttpStatusCode.OK, a.StatusCode);
        Assert.Equal(HttpStatusCode.OK, b.StatusCode);
        Assert.Equal(HttpStatusCode.TooManyRequests, encoreA.StatusCode);
    }
}
