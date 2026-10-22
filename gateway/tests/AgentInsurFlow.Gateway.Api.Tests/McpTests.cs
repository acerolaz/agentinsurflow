using System.Net;
using System.Text;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Hosting;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// TI de la route <c>/mcp</c> (Streamable HTTP, issue #58) et des écritures d'underwriting
/// (<c>PUT /api/contrats/{n}/brouillon|statut</c>, déjà couvertes par <c>underwriting-contrats</c>).
/// </summary>
public sealed class McpTests(Backends backends) : IClassFixture<Backends>
{
    private const string Rpc = """{"jsonrpc":"2.0","id":1,"method":"tools/list"}""";

    private static string JetonMcp(string[]? roles = null) => Creer(AudienceMcp, roles ?? ["Gestionnaire"]);

    private static async Task<HttpResponseMessage> Envoyer(
        HttpClient client, string verbe, string chemin, string? jeton, HttpContent? corps = null, string? traceparent = null)
    {
        using var requete = Requete(verbe, chemin, jeton);
        requete.Content = corps;
        if (traceparent is not null)
        {
            requete.Headers.Add("traceparent", traceparent);
        }
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    [Fact]
    public async Task Post_mcp_route_vers_le_backend_mcp()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", "/mcp", JetonMcp(), new StringContent(Rpc, Encoding.UTF8, "application/json"));

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var recu = Assert.Single(backends.Mcp.LogEntries).RequestMessage!;
        Assert.Equal("/mcp", recu.Path);
        Assert.Equal("POST", recu.Method);
        Assert.Equal(Rpc, recu.Body);
        Assert.StartsWith("application/json", Assert.Single(recu.Headers!["Content-Type"]), StringComparison.Ordinal);
        Assert.Empty(backends.Rag.LogEntries);
        Assert.Empty(backends.Underwriting.LogEntries);
    }

    [Fact]
    public async Task Get_mcp_route_vers_le_backend_mcp()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "GET", "/mcp", JetonMcp());

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Equal("GET", Assert.Single(backends.Mcp.LogEntries).RequestMessage!.Method);
    }

    [Fact]
    public async Task Put_mcp_405_sans_appel_backend()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "PUT", "/mcp", JetonMcp());

        Assert.Equal(HttpStatusCode.MethodNotAllowed, reponse.StatusCode);
        Assert.Empty(backends.Mcp.LogEntries);
    }

    [Fact]
    public async Task Sans_jeton_401()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", "/mcp", null);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        Assert.Equal("NON_AUTHENTIFIE", await AutorisationTests.Code(reponse));
        Assert.Empty(backends.Mcp.LogEntries);
    }

    [Fact]
    public async Task Jeton_audience_rag_403()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", "/mcp", Creer(AudienceRag, ["Gestionnaire"]));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Equal("ACCES_REFUSE", await AutorisationTests.Code(reponse));
        Assert.Empty(backends.Mcp.LogEntries);
    }

    [Fact]
    public async Task Sans_role_Gestionnaire_403()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, "POST", "/mcp", JetonMcp(["Ingestion"]));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Empty(backends.Mcp.LogEntries);
    }

    [Fact]
    public async Task Au_dela_de_la_limite_429_RetryAfter()
    {
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "5"), ("RateLimit:Mcp:PermitLimit", "1"));
        using var client = usine.CreateClient();
        var jeton = JetonMcp();

        await Envoyer(client, "POST", "/mcp", jeton);
        var deuxieme = await Envoyer(client, "POST", "/mcp", jeton);

        Assert.Equal(HttpStatusCode.TooManyRequests, deuxieme.StatusCode);
        Assert.Equal("TROP_DE_REQUETES", await AutorisationTests.Code(deuxieme));
        Assert.True(deuxieme.Headers.RetryAfter?.Delta > TimeSpan.Zero, "Retry-After absent");
        Assert.Single(backends.Mcp.LogEntries);
    }

    [Fact]
    public async Task Traceparent_relaye()
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();

        await Envoyer(client, "POST", "/mcp", JetonMcp(), traceparent: "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01");

        var entetes = Assert.Single(backends.Mcp.LogEntries).RequestMessage!.Headers!;
        Assert.Contains("0af7651916cd43dd8448eb211c80319c", Assert.Single(entetes["traceparent"]), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("brouillon")]
    [InlineData("statut")]
    public async Task Put_brouillon_et_statut_routes_vers_underwriting(string suffixe)
    {
        using var usine = backends.Gateway();
        using var client = usine.CreateClient();
        var chemin = $"/api/contrats/AIF-2026-0001/{suffixe}";

        var reponse = await Envoyer(client, "PUT", chemin, Creer(AudienceUnderwriting, ["Gestionnaire"]),
            new StringContent("{}", Encoding.UTF8, "application/json"));

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var recu = Assert.Single(backends.Underwriting.LogEntries).RequestMessage!;
        Assert.Equal(chemin, recu.Path);
        Assert.Equal("PUT", recu.Method);
        Assert.Empty(backends.Mcp.LogEntries);

        var sansRole = await Envoyer(client, "PUT", chemin, Creer(AudienceUnderwriting, ["Telemetrie"]));
        Assert.Equal(HttpStatusCode.Forbidden, sansRole.StatusCode);
    }

    // WireMock répond d'un bloc : un vrai Kestrel local sert l'événement 1, puis attend le feu vert du test
    [Fact]
    public async Task Sse_transmis_au_fil_de_l_eau()
    {
        var suite = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var builder = WebApplication.CreateSlimBuilder();
        builder.Configuration["urls"] = "http://127.0.0.1:0";
        await using var sse = builder.Build();
        sse.MapGet("/mcp", async (HttpContext ctx) =>
        {
            ctx.Response.ContentType = "text/event-stream";
            await ctx.Response.WriteAsync("data: un\n\n");
            await ctx.Response.Body.FlushAsync();
            await suite.Task;
            await ctx.Response.WriteAsync("data: deux\n\n");
        });
        await sse.StartAsync(TestContext.Current.CancellationToken);
        var adresse = sse.Urls.First();

        using var usine = backends.Gateway(("ReverseProxy:Clusters:mcp:Destinations:d1:Address", adresse));
        using var client = usine.CreateClient();
        using var requete = Requete("GET", "/mcp", JetonMcp());
        using var reponse = await client.SendAsync(requete, HttpCompletionOption.ResponseHeadersRead, TestContext.Current.CancellationToken);
        using var lecteur = new StreamReader(await reponse.Content.ReadAsStreamAsync(TestContext.Current.CancellationToken));

        // le backend n'a pas fini : si la gateway mettait en tampon, cette lecture ne reviendrait pas
        var premiere = await lecteur.ReadLineAsync(TestContext.Current.CancellationToken).AsTask().WaitAsync(TimeSpan.FromSeconds(10), TestContext.Current.CancellationToken);
        Assert.Equal("data: un", premiere);
        Assert.False(suite.Task.IsCompleted);

        suite.SetResult();
        await lecteur.ReadLineAsync(TestContext.Current.CancellationToken); // ligne vide
        Assert.Equal("data: deux", await lecteur.ReadLineAsync(TestContext.Current.CancellationToken));
    }
}
