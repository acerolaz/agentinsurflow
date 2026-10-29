using System.Net;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>TI : les notices produits publiques sous <c>/notices/</c> et le <c>robots.txt</c> (#45).</summary>
public sealed class NoticesTests(Backends backends) : IClassFixture<Backends>
{
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact]
    public async Task Index_servi_sans_jeton_avec_csp()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        using var reponse = await client.GetAsync(new Uri("/notices/", UriKind.Relative), Ct);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Equal("text/html", reponse.Content.Headers.ContentType?.MediaType);
        var csp = string.Join(";", reponse.Headers.GetValues("Content-Security-Policy"));
        Assert.Contains("default-src 'none'", csp, StringComparison.Ordinal);
        Assert.Contains("frame-ancestors 'none'", csp, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Notice_tiers_porte_ses_metadonnees()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        using var reponse = await client.GetAsync(new Uri("/notices/tiers.html", UriKind.Relative), Ct);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Contains("<meta name=\"doc_id\" content=\"tiers\">", await reponse.Content.ReadAsStringAsync(Ct), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Robots_txt_autorise_notices_seulement()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        using var reponse = await client.GetAsync(new Uri("/robots.txt", UriKind.Relative), Ct);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Equal("text/plain", reponse.Content.Headers.ContentType?.MediaType);
        Assert.Equal("User-agent: *\nAllow: /notices/\nDisallow: /\n", await reponse.Content.ReadAsStringAsync(Ct));
    }

    [Fact]
    public async Task Api_reste_protegee()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        using var reponse = await client.GetAsync(new Uri("/api/contrats", UriKind.Relative), Ct);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
    }
}
