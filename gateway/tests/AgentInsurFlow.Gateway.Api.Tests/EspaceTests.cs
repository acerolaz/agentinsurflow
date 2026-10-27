using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>TI : l'espace gestionnaire servi sous <c>/app/</c> (#103), sa configuration publique et sa CSP.</summary>
public sealed class EspaceTests(Backends backends) : IClassFixture<Backends>
{
    private static readonly (string, string)[] Reglages =
    [
        ("SWAGGER_CLIENT_ID", "client-public-test"),
        ("Espace:Authority", "https://login.microsoftonline.com/tenant-test"),
        ("Espace:Scopes:Cluster", "api://cluster/Evaluer"),
        ("Espace:Comptes:A", "gestionnaire.a@exemple.test"),
    ];

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact]
    public async Task Page_servie_sans_jeton_avec_csp()
    {
        using var usine = backends.Gateway(Reglages);
        using var client = usine.CreateClient();

        using var reponse = await client.GetAsync(new Uri("/app/", UriKind.Relative), Ct);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Equal("text/html", reponse.Content.Headers.ContentType?.MediaType);
        var csp = string.Join(";", reponse.Headers.GetValues("Content-Security-Policy"));
        Assert.Contains("script-src 'self'", csp, StringComparison.Ordinal);
        Assert.Contains("frame-ancestors 'none'", csp, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Msal_servi_avec_la_meme_csp()
    {
        using var usine = backends.Gateway(Reglages);
        using var client = usine.CreateClient();

        using var reponse = await client.GetAsync(new Uri("/app/vendor/msal-browser.min.js", UriKind.Relative), Ct);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.True(reponse.Headers.Contains("Content-Security-Policy"));
    }

    [Fact]
    public async Task Empreinte_sri_de_la_page_egale_celle_de_msal_servi()
    {
        using var usine = backends.Gateway(Reglages);
        using var client = usine.CreateClient();

        var page = await client.GetStringAsync(new Uri("/app/", UriKind.Relative), Ct);
        var msal = await client.GetByteArrayAsync(new Uri("/app/vendor/msal-browser.min.js", UriKind.Relative), Ct);

        Assert.Contains($"integrity=\"sha384-{Convert.ToBase64String(SHA384.HashData(msal))}\"", page, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Config_sans_secret()
    {
        using var usine = backends.Gateway(Reglages);
        using var client = usine.CreateClient();

        using var reponse = await client.GetAsync(new Uri("/app/config.json", UriKind.Relative), Ct);
        var texte = await reponse.Content.ReadAsStringAsync(Ct);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        using var json = JsonDocument.Parse(texte);
        Assert.Equal("client-public-test", json.RootElement.GetProperty("client_id").GetString());
        Assert.Equal("api://cluster/Evaluer", json.RootElement.GetProperty("scopes").GetProperty("cluster").GetString());
        Assert.Equal("gestionnaire.a@exemple.test", json.RootElement.GetProperty("comptes").GetProperty("A").GetString());
        Assert.DoesNotContain("secret", texte, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Swagger_toujours_a_la_racine()
    {
        using var usine = backends.Gateway(Reglages);
        using var client = usine.CreateClient();

        using var reponse = await client.GetAsync(new Uri("/", UriKind.Relative), Ct);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
    }

    [Fact]
    public async Task Etat_get_relaye_a_underwriting_avec_la_politique_gestionnaire()
    {
        using var usine = backends.Gateway(Reglages);
        using var client = usine.CreateClient();

        using var get = Requete("GET", "/api/contrats/AIF-2026-0001/etat", Creer(AudienceUnderwriting, ["Gestionnaire"]));
        using var lu = await client.SendAsync(get, Ct);
        using var put = Requete("PUT", "/api/contrats/AIF-2026-0001/etat", Creer(AudienceUnderwriting, ["Gestionnaire"]));
        using var ecrit = await client.SendAsync(put, Ct);

        Assert.Equal(HttpStatusCode.OK, lu.StatusCode);
        Assert.Equal("/api/contrats/AIF-2026-0001/etat", Assert.Single(backends.Underwriting.LogEntries).RequestMessage!.Path);
        Assert.Equal(HttpStatusCode.Forbidden, ecrit.StatusCode);
    }
}
