using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// Tests d'intégration (TI) : la page Swagger agrégée de la gateway (point d'entrée unique
/// de l'évaluateur) et le document OpenAPI de la gateway elle-même.
/// </summary>
public sealed class SwaggerTests : IDisposable
{
    private readonly WebApplicationFactory<Program> _usine = new WebApplicationFactory<Program>()
        .WithWebHostBuilder(b => b.UseSetting("SWAGGER_CLIENT_ID", "client-swagger-test").AvecEntraDeTest());
    private readonly HttpClient _client;

    public SwaggerTests() => _client = _usine.CreateClient();

    public void Dispose()
    {
        _client.Dispose();
        _usine.Dispose();
    }

    private async Task<string> PageSwagger()
    {
        var jeton = TestContext.Current.CancellationToken;
        var html = await _client.GetStringAsync(new Uri("/index.html", UriKind.Relative), jeton);
        var js = await _client.GetStringAsync(new Uri("/index.js", UriKind.Relative), jeton);
        return html + js;
    }

    [Fact]
    public async Task Racine_redirige_vers_la_page_swagger()
    {
        using var client = _usine.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false });

        var reponse = await client.GetAsync(new Uri("/", UriKind.Relative), TestContext.Current.CancellationToken);

        Assert.True(reponse.StatusCode is HttpStatusCode.MovedPermanently or HttpStatusCode.Redirect);
        Assert.EndsWith("index.html", reponse.Headers.Location!.ToString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("/openapi/v1.json")]
    [InlineData("/rag/openapi.json")]
    [InlineData("/underwriting/openapi/v1.json")]
    [InlineData("/cluster/openapi.json")]
    public async Task Page_swagger_liste_les_documents(string document)
    {
        var page = await PageSwagger();

        Assert.Contains("swagger-ui", page, StringComparison.Ordinal);
        Assert.Contains(document, page, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Page_swagger_se_connecte_a_Entra_en_PKCE()
    {
        var page = await PageSwagger();

        Assert.Contains("client-swagger-test", page, StringComparison.Ordinal);
        Assert.Contains("\"usePkceWithAuthorizationCodeGrant\":true", page.Replace(" ", "", StringComparison.Ordinal), StringComparison.Ordinal);
    }

    [Fact]
    public async Task OpenApi_de_la_gateway_documente_health()
    {
        var reponse = await _client.GetAsync(new Uri("/openapi/v1.json", UriKind.Relative), TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        using var json = JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken));
        Assert.True(json.RootElement.GetProperty("paths").TryGetProperty("/health", out _));
    }
}
