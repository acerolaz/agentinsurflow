using System.Net;
using System.Text;
using Azure;
using Azure.Core;
using Azure.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>TI de la route <c>/api/calcul/*</c> : jeton d'application (rôle <c>Calcul</c>) du serveur MCP vers la Function de calcul.</summary>
public sealed class CalculTests(Backends backends) : IClassFixture<Backends>
{
    private static string JetonCalcul(string[]? roles = null) => Creer(AudienceCalcul, roles ?? ["Calcul"]);

    private static async Task<HttpResponseMessage> Envoyer(HttpClient client, string chemin, string? jeton)
    {
        using var requete = Requete("POST", chemin, jeton);
        requete.Content = new StringContent("{}", Encoding.UTF8, "application/json");
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    private const string Portee = "api://calcul-test/.default";
    private const string JetonGateway = "jeton-de-la-gateway";

    private sealed class FauxCredential(Exception? echec = null) : TokenCredential
    {
        public List<string[]> Portees { get; } = [];

        public override AccessToken GetToken(TokenRequestContext c, CancellationToken ct) =>
            GetTokenAsync(c, ct).AsTask().GetAwaiter().GetResult();

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext c, CancellationToken ct)
        {
            Portees.Add(c.Scopes);
            return echec is null
                ? new(new AccessToken(JetonGateway, DateTimeOffset.UtcNow.AddHours(1)))
                : throw echec;
        }
    }

    private WebApplicationFactory<Program> GatewayAvecCredential(FauxCredential credential, bool avecPortee = true) =>
        (avecPortee ? backends.Gateway(("Calcul:Portee", Portee)) : backends.Gateway())
            .WithWebHostBuilder(b => b.ConfigureTestServices(s => s.AddSingleton<TokenCredential>(credential)));

    [Fact]
    public async Task Post_calcul_evaluer_arrive_en_api_evaluer_avec_le_jeton_de_la_gateway()
    {
        var credential = new FauxCredential();
        using var usine = GatewayAvecCredential(credential);
        using var client = usine.CreateClient();
        var jeton = JetonCalcul();

        var reponse = await Envoyer(client, "/api/calcul/evaluer", jeton);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var recu = Assert.Single(backends.Calcul.LogEntries).RequestMessage!;
        Assert.Equal("/api/evaluer", recu.Path);
        Assert.Equal($"Bearer {JetonGateway}", Assert.Single(recu.Headers!["Authorization"]));
        Assert.Equal(Portee, Assert.Single(Assert.Single(credential.Portees)));
        Assert.Empty(backends.Mcp.LogEntries);
    }

    [Fact]
    public async Task Sans_portee_configuree_aucun_Authorization_relaye()
    {
        var credential = new FauxCredential();
        using var usine = GatewayAvecCredential(credential, avecPortee: false);
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "/api/calcul/evaluer", JetonCalcul());

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var recu = Assert.Single(backends.Calcul.LogEntries).RequestMessage!;
        Assert.False(recu.Headers!.ContainsKey("Authorization"));
        Assert.Empty(credential.Portees);
    }

    [Fact]
    public async Task Credential_en_echec_502_CALCUL_INDISPONIBLE_sans_detail_du_jeton()
    {
        var credential = new FauxCredential(new AuthenticationFailedException("secret-interne"));
        using var usine = GatewayAvecCredential(credential);
        using var client = usine.CreateClient();
        var jeton = JetonCalcul();

        var reponse = await Envoyer(client, "/api/calcul/evaluer", jeton);

        Assert.Equal(HttpStatusCode.BadGateway, reponse.StatusCode);
        Assert.Equal("CALCUL_INDISPONIBLE", await AutorisationTests.Code(reponse));
        var corps = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        Assert.DoesNotContain("secret-interne", corps, StringComparison.Ordinal);
        Assert.DoesNotContain(jeton, corps, StringComparison.Ordinal);
        Assert.Empty(backends.Calcul.LogEntries);
    }

    [Fact]
    public async Task Health_calcul_et_autres_routes_ne_declenchent_aucun_echange()
    {
        var credential = new FauxCredential();
        using var usine = GatewayAvecCredential(credential);
        using var client = usine.CreateClient();

        await client.GetAsync(new Uri("/health/calcul", UriKind.Relative), TestContext.Current.CancellationToken);
        var jeton = Creer(AudienceMcp, ["Gestionnaire"]);
        using var requete = Requete("POST", "/mcp", jeton);
        await client.SendAsync(requete, TestContext.Current.CancellationToken);

        Assert.Empty(credential.Portees);
        var recu = Assert.Single(backends.Mcp.LogEntries).RequestMessage!;
        Assert.Equal($"Bearer {jeton}", Assert.Single(recu.Headers!["Authorization"]));
    }

    [Fact]
    public async Task Audience_GUID_de_l_application_acceptee()
    {
        const string guid = "11111111-1111-1111-1111-111111111111";
        using var usine = backends.Gateway(("Entra:Audiences:calcul:1", guid));
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "/api/calcul/evaluer", Creer(guid, ["Calcul"]));

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Single(backends.Calcul.LogEntries);
    }

    [Fact]
    public async Task Sans_jeton_401()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "/api/calcul/evaluer", null);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        Assert.Equal("NON_AUTHENTIFIE", await AutorisationTests.Code(reponse));
        Assert.Empty(backends.Calcul.LogEntries);
    }

    [Fact]
    public async Task Sans_role_Calcul_403()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "/api/calcul/evaluer", JetonCalcul(["Gestionnaire"]));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Equal("ACCES_REFUSE", await AutorisationTests.Code(reponse));
        Assert.Empty(backends.Calcul.LogEntries);
    }

    [Fact]
    public async Task Role_Calcul_mauvaise_audience_403()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "/api/calcul/evaluer", Creer(AudienceMcp, ["Calcul"]));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Empty(backends.Calcul.LogEntries);
    }

    [Fact]
    public async Task Au_dela_de_la_limite_429()
    {
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "5"), ("RateLimit:Calcul:PermitLimit", "1"));
        using var client = usine.CreateClient();
        var jeton = JetonCalcul();

        var premiere = await Envoyer(client, "/api/calcul/evaluer", jeton);
        var deuxieme = await Envoyer(client, "/api/calcul/evaluer", jeton);

        Assert.Equal(HttpStatusCode.OK, premiere.StatusCode);
        Assert.Equal(HttpStatusCode.TooManyRequests, deuxieme.StatusCode);
        Assert.Equal("TROP_DE_REQUETES", await AutorisationTests.Code(deuxieme));
        Assert.Single(backends.Calcul.LogEntries);
    }

    [Fact]
    public async Task Health_calcul_anonyme_route_vers_api_sante()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await client.GetAsync(new Uri("/health/calcul", UriKind.Relative), TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Equal("/api/sante", Assert.Single(backends.Calcul.LogEntries).RequestMessage!.Path);
    }
}
