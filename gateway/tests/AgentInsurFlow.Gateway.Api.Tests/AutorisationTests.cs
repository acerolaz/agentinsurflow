using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// TI de la sécurité de la gateway (S3-25) : jeton Entra validé, rôle et audience exigés par route,
/// refus par défaut. Les services revalident le jeton ; ces tests ne prouvent que la première barrière.
/// </summary>
public sealed class AutorisationTests : IClassFixture<Backends>, IDisposable
{
    private readonly Backends _backends;
    private readonly WebApplicationFactory<Program> _usine;
    private readonly HttpClient _client;

    public AutorisationTests(Backends backends)
    {
        _backends = backends;
        _backends.Rag.ResetLogEntries();
        _backends.Underwriting.ResetLogEntries();
        _backends.Mcp.ResetLogEntries();
        _usine = new WebApplicationFactory<Program>().WithWebHostBuilder(b => b
            .UseSetting("ReverseProxy:Clusters:rag:Destinations:d1:Address", backends.Rag.Url)
            .UseSetting("ReverseProxy:Clusters:underwriting:Destinations:d1:Address", backends.Underwriting.Url)
            .UseSetting("ReverseProxy:Clusters:mcp:Destinations:d1:Address", backends.Mcp.Url)
            .AvecEntraDeTest());
        _client = _usine.CreateClient();
    }

    public void Dispose()
    {
        _client.Dispose();
        _usine.Dispose();
    }

    private Task<HttpResponseMessage> Envoyer(string verbe, string chemin, string? jeton = null)
    {
        using var requete = Requete(verbe, chemin, jeton);
        return _client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    private void AucunAppelTransmis()
    {
        Assert.Empty(_backends.Rag.LogEntries);
        Assert.Empty(_backends.Underwriting.LogEntries);
    }

    /// <summary>Le champ <c>code</c> d'une réponse ProblemDetails (partagé avec <see cref="DebitTests"/>).</summary>
    internal static async Task<string> Code(HttpResponseMessage reponse)
    {
        Assert.Equal("application/problem+json", reponse.Content.Headers.ContentType?.MediaType);
        using var json = JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken));
        return json.RootElement.GetProperty("code").GetString()!;
    }

    // Table route → rôle → service (S3-25)
    public static TheoryData<string, string, string, string> RoutesProtegees => new()
    {
        { "POST", "/api/reponses", "rag", "Gestionnaire" },
        { "POST", "/api/ingestions", "rag", "Ingestion" },
        { "GET", "/api/ingestions/42", "rag", "Ingestion" },
        { "GET", "/api/extraits?question=bonus", "rag", "Gestionnaire" },
        { "GET", "/api/documents/LEGIARTI000006800836", "rag", "Gestionnaire" },
        { "GET", "/api/contrats", "underwriting", "Gestionnaire" },
        { "GET", "/api/contrats/AIF-2026-0001", "underwriting", "Gestionnaire" },
        { "GET", "/api/traces/0af7651916cd43dd8448eb211c80319c", "underwriting", "Gestionnaire" },
        { "POST", "/v1/traces", "underwriting", "Telemetrie" },
    };

    [Theory]
    [MemberData(nameof(RoutesProtegees))]
    public async Task Sans_jeton_401_ProblemDetails_sans_appel_backend(string verbe, string chemin, string backend, string role)
    {
        _ = (backend, role);

        var reponse = await Envoyer(verbe, chemin);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        Assert.Equal("Bearer", Assert.Single(reponse.Headers.WwwAuthenticate).Scheme);
        Assert.Equal("NON_AUTHENTIFIE", await Code(reponse));
        AucunAppelTransmis();
    }

    [Fact]
    public async Task Jeton_signe_par_une_autre_cle_401()
    {
        var jeton = Creer(AudienceRag, ["Gestionnaire"], cle: NouvelleCle("cle-pirate"));

        var reponse = await Envoyer("POST", "/api/reponses", jeton);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        AucunAppelTransmis();
    }

    [Fact]
    public async Task Jeton_expire_401()
    {
        var jeton = Creer(AudienceRag, ["Gestionnaire"], expire: DateTime.UtcNow.AddMinutes(-10));

        var reponse = await Envoyer("POST", "/api/reponses", jeton);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        AucunAppelTransmis();
    }

    [Fact]
    public async Task Emetteur_d_un_autre_tenant_401()
    {
        var jeton = Creer(AudienceRag, ["Gestionnaire"], emetteur: "https://login.microsoftonline.com/autre-tenant/v2.0");

        var reponse = await Envoyer("POST", "/api/reponses", jeton);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        AucunAppelTransmis();
    }

    [Fact]
    public async Task Role_manquant_403()
    {
        var jeton = Creer(AudienceRag, ["Gestionnaire"]);

        var reponse = await Envoyer("POST", "/api/ingestions", jeton);

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Equal("ACCES_REFUSE", await Code(reponse));
        AucunAppelTransmis();
    }

    [Fact]
    public async Task Audience_d_un_autre_service_403()
    {
        var jeton = Creer(AudienceUnderwriting, ["Gestionnaire"]);

        var reponse = await Envoyer("POST", "/api/reponses", jeton);

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        AucunAppelTransmis();
    }

    [Fact]
    public async Task Role_Telemetrie_ne_donne_pas_les_contrats_403()
    {
        var jeton = Creer(AudienceUnderwriting, ["Telemetrie"]);

        var reponse = await Envoyer("GET", "/api/contrats", jeton);

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        AucunAppelTransmis();
    }

    [Theory]
    [MemberData(nameof(RoutesProtegees))]
    public async Task Bon_role_et_bonne_audience_transmis(string verbe, string chemin, string backend, string role)
    {
        var jeton = Creer(Audience(backend), [role]);

        var reponse = await Envoyer(verbe, chemin, jeton);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var (vise, autre) = backend == "rag"
            ? (_backends.Rag, _backends.Underwriting)
            : (_backends.Underwriting, _backends.Rag);
        var entetes = Assert.Single(vise.LogEntries).RequestMessage!.Headers!;
        Assert.Equal($"Bearer {jeton}", Assert.Single(entetes["Authorization"]));
        Assert.Empty(autre.LogEntries);
    }

    [Theory]
    [InlineData("v1")]
    [InlineData("v2")]
    public async Task Jetons_v1_et_v2_acceptes(string version)
    {
        var jeton = Creer(AudienceRag, ["Gestionnaire"], emetteur: version == "v1" ? EmetteurV1 : EmetteurV2);

        var reponse = await Envoyer("POST", "/api/reponses", jeton);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
    }

    [Fact]
    public async Task Audiences_en_liste_separee_par_des_virgules()
    {
        // RAG_API_AUDIENCES : la même liste que celle lue par rag (ID client et api://<ID client>)
        using var usine = _backends.Gateway(("Entra:Audiences:rag:0", "id-client-rag, api://id-client-rag"));
        using var client = usine.CreateClient();

        foreach (var audience in new[] { "id-client-rag", "api://id-client-rag" })
        {
            using var requete = Requete("POST", "/api/reponses", Creer(audience, ["Gestionnaire"]));
            var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
            Assert.True(reponse.StatusCode == HttpStatusCode.OK, $"{audience} → {reponse.StatusCode}");
        }
    }

    [Theory]
    [InlineData("/")]
    [InlineData("/index.html")]
    [InlineData("/openapi/v1.json")]
    [InlineData("/rag/openapi.json")]
    [InlineData("/underwriting/openapi/v1.json")]
    [InlineData("/health")]
    [InlineData("/health/rag")]
    [InlineData("/health/underwriting")]
    [InlineData("/health/mcp")]
    public async Task Documentation_et_sante_sans_jeton(string chemin)
    {
        var reponse = await Envoyer("GET", chemin);

        Assert.True(reponse.IsSuccessStatusCode || reponse.StatusCode == HttpStatusCode.MovedPermanently, $"{chemin} → {reponse.StatusCode}");
    }

    // Les routes de documentation sont anonymes : elles ne doivent ouvrir QUE le document OpenAPI,
    // sinon /rag/api/reponses atteindrait rag sans jeton ni limite de débit.
    [Theory]
    [InlineData("POST", "/rag/api/reponses")]
    [InlineData("GET", "/rag/api/documents/LEGIARTI000006800836")]
    [InlineData("GET", "/rag/")]
    [InlineData("GET", "/underwriting/api/contrats")]
    [InlineData("POST", "/underwriting/v1/traces")]
    public async Task Documentation_n_ouvre_que_le_document_OpenAPI(string verbe, string chemin)
    {
        var reponse = await Envoyer(verbe, chemin);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        AucunAppelTransmis();
    }

    [Fact]
    public async Task Chemin_inconnu_401_sans_jeton_404_avec_jeton()
    {
        var sansJeton = await Envoyer("GET", "/inconnu");
        var avecJeton = await Envoyer("GET", "/inconnu", Creer(AudienceRag, ["Gestionnaire"]));

        Assert.Equal(HttpStatusCode.Unauthorized, sansJeton.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, avecJeton.StatusCode);
        AucunAppelTransmis();
    }

    [Fact]
    public void Toutes_les_routes_declarent_une_politique()
    {
        var routes = _usine.Services.GetRequiredService<IConfiguration>().GetSection("ReverseProxy:Routes").GetChildren().ToList();

        Assert.NotEmpty(routes);
        Assert.All(routes, r => Assert.False(string.IsNullOrWhiteSpace(r["AuthorizationPolicy"]), $"route {r.Key} sans AuthorizationPolicy"));
    }
}
