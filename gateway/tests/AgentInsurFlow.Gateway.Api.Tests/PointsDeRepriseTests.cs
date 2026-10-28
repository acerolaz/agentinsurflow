using System.Net;
using System.Text;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>TI de <c>/api/points-de-reprise/**</c> (D106) : relayé à underwriting-admin pour le seul cluster.</summary>
public sealed class PointsDeRepriseTests(Backends backends) : IClassFixture<Backends>
{
    private const string Chemin = "/api/points-de-reprise/AIF-2026-0001/ecritures";
    private const string Corps = """{"ecritures":[{"idx":-1}]}""";

    private static async Task<HttpResponseMessage> Put(HttpClient client, string jeton, string query = "")
    {
        using var requete = Requete("PUT", Chemin + query, jeton);
        requete.Content = new StringContent(Corps, Encoding.UTF8, "application/json");
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    [Fact]
    public async Task Cluster_relaye_vers_underwriting()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Put(client, Creer(AudienceUnderwriting, ["PointsDeReprise"], azp: ClientCluster), "?ns=&id=x");

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var recu = Assert.Single(backends.Underwriting.LogEntries).RequestMessage!;
        Assert.Equal(Chemin, recu.Path);
        Assert.Equal("x", Assert.Single(recu.Query!["id"]));
        Assert.Equal("", Assert.Single(recu.Query["ns"]));
        Assert.Equal("PUT", recu.Method);
        Assert.Equal(Corps, recu.Body);
    }

    [Fact]
    public async Task Points_de_reprise_refuses_a_un_autre_azp()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var autre = await Put(client, Creer(AudienceUnderwriting, ["PointsDeReprise"], azp: ClientMcp));
        var sans = await Put(client, Creer(AudienceUnderwriting, ["PointsDeReprise"]));

        Assert.Equal(HttpStatusCode.Forbidden, autre.StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, sans.StatusCode);
        Assert.Empty(backends.Underwriting.LogEntries);
    }

    [Fact]
    public async Task Gestionnaire_refuse()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Put(client, Creer(AudienceUnderwriting, ["Gestionnaire"], azp: ClientCluster));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Empty(backends.Underwriting.LogEntries);
    }

    [Fact]
    public async Task Sans_client_cluster_configure_route_fermee()
    {
        using var usine = backends.Gateway(("Entra:ClusterClientId", ""));
        using var client = usine.CreateClient();

        // jeton parfaitement valide : seule la configuration vide ferme la route
        var reponse = await Put(client, Creer(AudienceUnderwriting, ["PointsDeReprise"], azp: ClientCluster));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Empty(backends.Underwriting.LogEntries);
    }

    [Fact]
    public async Task Jamais_limite_en_debit()
    {
        // les évaluations concurrentes du cluster écrivent un point par étape : pas de 429
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "2"));
        using var client = usine.CreateClient();
        var jeton = Creer(AudienceUnderwriting, ["PointsDeReprise"], azp: ClientCluster);

        for (var i = 0; i < 6; i++)
        {
            var reponse = await Put(client, jeton);
            Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        }
    }
}
