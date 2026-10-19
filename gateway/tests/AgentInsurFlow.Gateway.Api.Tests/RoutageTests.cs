using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using WireMock.RequestBuilders;
using WireMock.ResponseBuilders;
using WireMock.Server;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// Tests d'intégration (TI) : la vraie gateway en mémoire, devant deux backends WireMock.
/// Forme « diamant » assumée : un proxy pur n'a pas de règle métier à tester unitairement.
/// Les routes protégées reçoivent un jeton valide ; la sécurité est testée dans <see cref="AutorisationTests"/>.
/// </summary>
public sealed class RoutageTests : IClassFixture<Backends>, IDisposable
{
    private readonly Backends _backends;
    private readonly WebApplicationFactory<Program> _usine;
    private readonly HttpClient _client;

    public RoutageTests(Backends backends)
    {
        _backends = backends;
        _backends.Rag.ResetLogEntries();
        _backends.Underwriting.ResetLogEntries();
        _usine = new WebApplicationFactory<Program>().WithWebHostBuilder(b => b
            .UseSetting("ReverseProxy:Clusters:rag:Destinations:d1:Address", backends.Rag.Url)
            .UseSetting("ReverseProxy:Clusters:underwriting:Destinations:d1:Address", backends.Underwriting.Url)
            .UseSetting("APP_VERSION", "abc123")
            .UseSetting("APP_RELEASE", "v0.2.0")
            .AvecEntraDeTest());
        _client = _usine.CreateClient();
    }

    public void Dispose()
    {
        _client.Dispose();
        _usine.Dispose();
    }

    private Task<HttpResponseMessage> Envoyer(HttpRequestMessage requete) =>
        _client.SendAsync(requete, TestContext.Current.CancellationToken);

    private static string JetonComplet(string backend) => Creer(Audience(backend), TousLesRoles);

    // Contrat REST (S3-24) : une route par ressource, au pluriel
    [Theory]
    [InlineData("/api/reponses", "rag", "/api/reponses")]
    [InlineData("/api/ingestions", "rag", "/api/ingestions")]
    [InlineData("/api/ingestions/42", "rag", "/api/ingestions/42")]
    [InlineData("/api/extraits?question=bonus", "rag", "/api/extraits")]
    [InlineData("/api/documents/LEGIARTI000006800836", "rag", "/api/documents/LEGIARTI000006800836")]
    [InlineData("/rag/openapi.json", "rag", "/openapi.json")]
    [InlineData("/api/contrats", "underwriting", "/api/contrats")]
    [InlineData("/api/contrats/AIF-2026-0001", "underwriting", "/api/contrats/AIF-2026-0001")]
    [InlineData("/api/traces/0af7651916cd43dd8448eb211c80319c", "underwriting", "/api/traces/0af7651916cd43dd8448eb211c80319c")]
    [InlineData("/v1/traces", "underwriting", "/v1/traces")]
    [InlineData("/underwriting/openapi/v1.json", "underwriting", "/openapi/v1.json")]
    public async Task Route_vers_le_bon_backend(string chemin, string backend, string cheminRecu)
    {
        using var requete = Requete("GET", chemin, JetonComplet(backend));
        var reponse = await Envoyer(requete);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var (vise, autre) = backend == "rag"
            ? (_backends.Rag, _backends.Underwriting)
            : (_backends.Underwriting, _backends.Rag);
        Assert.Equal(cheminRecu, Assert.Single(vise.LogEntries).RequestMessage!.Path);
        Assert.Empty(autre.LogEntries);
    }

    // Chemin inconnu, et anciennes routes de style RPC du plan v1 : plus routées
    [Theory]
    [InlineData("/inconnu")]
    [InlineData("/api/agent")]
    [InlineData("/api/inconnue")]
    [InlineData("/v1/ingestion")]
    [InlineData("/internal/rag/search")]
    [InlineData("/internal/sql/contrats")]
    public async Task Chemin_non_route_404_sans_appel_backend(string chemin)
    {
        using var requete = Requete("GET", chemin, JetonComplet("rag"));
        var reponse = await Envoyer(requete);

        Assert.Equal(HttpStatusCode.NotFound, reponse.StatusCode);
        Assert.Empty(_backends.Rag.LogEntries);
        Assert.Empty(_backends.Underwriting.LogEntries);
    }

    [Theory]
    [InlineData("/rag/openapi.json", "rag", "/rag")]
    [InlineData("/underwriting/openapi/v1.json", "underwriting", "/underwriting")]
    public async Task Documentation_recoit_son_prefixe_public(string chemin, string backend, string prefixe)
    {
        await _client.GetAsync(new Uri(chemin, UriKind.Relative), TestContext.Current.CancellationToken);

        var vise = backend == "rag" ? _backends.Rag : _backends.Underwriting;
        var entetes = Assert.Single(vise.LogEntries).RequestMessage!.Headers!;
        Assert.Equal(prefixe, Assert.Single(entetes["X-Forwarded-Prefix"]));
    }

    [Fact]
    public async Task XForwardedPrefix_du_client_ne_passe_pas()
    {
        using var requete = Requete("GET", "/api/contrats", JetonComplet("underwriting"));
        requete.Headers.Add("X-Forwarded-Prefix", "/pirate");

        await Envoyer(requete);

        var entetes = Assert.Single(_backends.Underwriting.LogEntries).RequestMessage!.Headers!;
        var prefixe = entetes.TryGetValue("X-Forwarded-Prefix", out var valeurs) ? string.Join(",", valeurs) : "";
        Assert.DoesNotContain("/pirate", prefixe, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Transmet_XForwardedFor_reecrit()
    {
        using var requete = Requete("POST", "/v1/traces", JetonComplet("underwriting"));
        requete.Headers.Add("X-Forwarded-For", "10.0.0.1");

        await Envoyer(requete);

        var entetes = Assert.Single(_backends.Underwriting.LogEntries).RequestMessage!.Headers!;
        var xff = entetes.TryGetValue("X-Forwarded-For", out var valeurs) ? string.Join(",", valeurs) : "";
        Assert.DoesNotContain("10.0.0.1", xff, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Transmet_Authorization_et_traceparent_sans_les_modifier()
    {
        const string traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01";
        var jeton = Creer(AudienceUnderwriting, ["Gestionnaire"]);
        using var requete = Requete("GET", "/api/contrats", jeton);
        requete.Headers.Add("traceparent", traceparent);

        await Envoyer(requete);

        var entetes = Assert.Single(_backends.Underwriting.LogEntries).RequestMessage!.Headers!;
        Assert.Equal($"Bearer {jeton}", Assert.Single(entetes["Authorization"]));
        Assert.Contains("0af7651916cd43dd8448eb211c80319c", Assert.Single(entetes["traceparent"]), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Health_repond_sans_backend()
    {
        var reponse = await _client.GetAsync(new Uri("/health", UriKind.Relative), TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        using var json = JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken));
        Assert.Equal("ok", json.RootElement.GetProperty("statut").GetString());
        Assert.Equal("abc123", json.RootElement.GetProperty("version").GetString());
        Assert.Equal("v0.2.0", json.RootElement.GetProperty("release").GetString());
        Assert.Empty(_backends.Rag.LogEntries);
        Assert.Empty(_backends.Underwriting.LogEntries);
    }

    [Theory]
    [InlineData("/health/rag", "rag")]
    [InlineData("/health/underwriting", "underwriting")]
    public async Task Health_des_services_route_vers_leur_health(string chemin, string backend)
    {
        await _client.GetAsync(new Uri(chemin, UriKind.Relative), TestContext.Current.CancellationToken);

        var vise = backend == "rag" ? _backends.Rag : _backends.Underwriting;
        Assert.Equal("/health", Assert.Single(vise.LogEntries).RequestMessage!.Path);
    }
}

/// <summary>Deux faux backends partagés par les tests de la classe ; ils répondent 200 à tout.</summary>
public sealed class Backends : IDisposable
{
    public WireMockServer Rag { get; } = Demarrer();
    public WireMockServer Underwriting { get; } = Demarrer();

    private static WireMockServer Demarrer()
    {
        var serveur = WireMockServer.Start();
        serveur.Given(Request.Create().UsingAnyMethod()).RespondWith(Response.Create().WithStatusCode(200));
        return serveur;
    }

    public void Dispose()
    {
        Rag.Stop();
        Underwriting.Stop();
    }
}
