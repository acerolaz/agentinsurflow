using System.Net;
using System.Text;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// TI des routes publiques du cluster d'agents (#7) : <c>POST /v1/souscriptions/{numero}/evaluation</c> et <c>/revue</c>.
/// La gateway relaie le jeton du gestionnaire (audience cluster), comme pour <c>/mcp</c> : elle ne l'échange pas.
/// </summary>
public sealed class ClusterTests(Backends backends) : IClassFixture<Backends>
{
    private const string Route = "/v1/souscriptions/AIF-2026-0001/evaluation";
    private const string Revue = """{"decision":"ACCEPTE","validation":"VALIDEE","motif":"ok"}""";

    private static string JetonCluster(string[]? roles = null) => Creer(AudienceCluster, roles ?? ["Gestionnaire"]);

    private static async Task<HttpResponseMessage> Envoyer(HttpClient client, string verbe, string chemin, string? jeton, string? corps = null)
    {
        using var requete = Requete(verbe, chemin, jeton);
        if (corps is not null)
        {
            requete.Content = new StringContent(corps, Encoding.UTF8, "application/json");
        }
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    [Fact]
    public async Task Sans_jeton_401()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", Route, null);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        Assert.Equal("NON_AUTHENTIFIE", await AutorisationTests.Code(reponse));
        Assert.Empty(backends.Cluster.LogEntries);
    }

    [Theory]
    [InlineData("/v1/souscriptions/AIF-2026-0001/evaluation", "/evaluations/AIF-2026-0001", null)]
    [InlineData("/v1/souscriptions/AIF-2026-0001/revue", "/evaluations/AIF-2026-0001/revue", Revue)]
    public async Task Gestionnaire_relaye_vers_le_cluster_avec_son_jeton(string chemin, string cheminRecu, string? corps)
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();
        var jeton = JetonCluster();

        var reponse = await Envoyer(client, "POST", chemin, jeton, corps);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var recu = Assert.Single(backends.Cluster.LogEntries).RequestMessage!;
        Assert.Equal(cheminRecu, recu.Path);
        Assert.Equal("POST", recu.Method);
        Assert.Equal($"Bearer {jeton}", Assert.Single(recu.Headers!["Authorization"]));
        Assert.Empty(backends.Mcp.LogEntries);
        Assert.Empty(backends.Underwriting.LogEntries);
    }

    [Theory]
    [InlineData("GET")]
    [InlineData("PUT")]
    [InlineData("DELETE")]
    [InlineData("PATCH")]
    [InlineData("HEAD")]
    [InlineData("OPTIONS")]
    public async Task Autre_verbe_405_sans_appel_backend(string verbe)
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, verbe, Route, JetonCluster());

        Assert.Equal(HttpStatusCode.MethodNotAllowed, reponse.StatusCode);
        Assert.Empty(backends.Cluster.LogEntries);
    }

    [Fact]
    public async Task Jeton_sans_claim_roles_403()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", Route, Creer(AudienceCluster, []));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Empty(backends.Cluster.LogEntries);
    }

    [Fact]
    public async Task Les_routes_internes_du_cluster_ne_sont_pas_exposees()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", "/evaluations/AIF-2026-0001", JetonCluster());

        Assert.Equal(HttpStatusCode.NotFound, reponse.StatusCode);
        Assert.Empty(backends.Cluster.LogEntries);
    }

    [Theory]
    [InlineData(AudienceMcp, "Gestionnaire")]
    [InlineData(AudienceRag, "Gestionnaire")]
    [InlineData(AudienceCluster, "Ingestion")]
    public async Task Mauvaise_audience_ou_role_403(string audience, string role)
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", Route, Creer(audience, [role]));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Equal("ACCES_REFUSE", await AutorisationTests.Code(reponse));
        Assert.Empty(backends.Cluster.LogEntries);
    }

    [Fact]
    public async Task Jeton_cluster_n_ouvre_pas_le_mcp()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", "/mcp", JetonCluster());

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Empty(backends.Mcp.LogEntries);
    }

    [Fact]
    public async Task Au_dela_de_la_limite_429_RetryAfter()
    {
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "5"), ("RateLimit:Cluster:PermitLimit", "1"));
        using var client = usine.CreateClient();
        var jeton = JetonCluster();

        await Envoyer(client, "POST", Route, jeton);
        var deuxieme = await Envoyer(client, "POST", Route, jeton);

        Assert.Equal(HttpStatusCode.TooManyRequests, deuxieme.StatusCode);
        Assert.Equal("TROP_DE_REQUETES", await AutorisationTests.Code(deuxieme));
        Assert.True(deuxieme.Headers.RetryAfter?.Delta > TimeSpan.Zero, "Retry-After absent");
        Assert.Single(backends.Cluster.LogEntries);
    }
}
