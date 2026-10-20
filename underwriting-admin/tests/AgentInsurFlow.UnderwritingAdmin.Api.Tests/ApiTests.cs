using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>Tests d'intégration (TI) : l'API complète en mémoire (<c>WebApplicationFactory</c>).</summary>
public sealed class ApiTests : IDisposable
{
    private readonly WebApplicationFactory<Program> _usine = new();
    private readonly HttpClient _client;

    public ApiTests() => _client = _usine.CreateClient();

    public void Dispose()
    {
        _client.Dispose();
        _usine.Dispose();
    }

    private async Task<JsonElement> Json(string chemin, HttpStatusCode attendu, string? prefixe = null)
    {
        using var requete = new HttpRequestMessage(HttpMethod.Get, chemin);
        if (prefixe is not null)
        {
            requete.Headers.Add("X-Forwarded-Prefix", prefixe);
        }
        using var reponse = await _client.SendAsync(requete, TestContext.Current.CancellationToken);
        Assert.Equal(attendu, reponse.StatusCode);
        return JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken)).RootElement;
    }

    [Fact]
    public async Task Health_200_sans_jeton()
    {
        var sante = await Json("/health", HttpStatusCode.OK);

        Assert.Equal("ok", sante.GetProperty("statut").GetString());
        Assert.Equal("dev", sante.GetProperty("version").GetString());
        Assert.Equal("dev", sante.GetProperty("release").GetString());
    }

    [Fact]
    public async Task Route_protegee_sans_jeton_401()
    {
        using var reponse = await _client.GetAsync(new Uri("/api/inconnue", UriKind.Relative), TestContext.Current.CancellationToken);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        using var probleme = JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken));
        Assert.Equal("NON_AUTHENTIFIE", probleme.RootElement.GetProperty("code").GetString());
    }

    [Fact]
    public async Task OpenApi_expose_le_schema_de_securite()
    {
        var doc = await Json("/openapi/v1.json", HttpStatusCode.OK);

        var bearer = doc.GetProperty("components").GetProperty("securitySchemes").GetProperty("Bearer");
        Assert.Equal("http", bearer.GetProperty("type").GetString());
        Assert.Equal("bearer", bearer.GetProperty("scheme").GetString());
    }

    [Fact]
    public async Task OpenApi_ne_declare_pas_de_servers_meme_derriere_la_gateway()
    {
        var doc = await Json("/openapi/v1.json", HttpStatusCode.OK, prefixe: "/underwriting");

        Assert.False(doc.TryGetProperty("servers", out _));
    }
}
