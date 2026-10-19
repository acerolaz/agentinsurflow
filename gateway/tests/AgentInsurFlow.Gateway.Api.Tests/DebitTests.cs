using System.Net;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// TI de la limitation de débit (S3-27, issue #13) : fenêtre fixe par utilisateur (<c>oid</c>) ou par IP,
/// limite plus stricte sur <c>POST /api/reponses</c>, sondes jamais limitées. Limites réduites par réglage.
/// </summary>
public sealed class DebitTests(Backends backends) : IClassFixture<Backends>
{
    private static async Task<HttpResponseMessage> Envoyer(HttpClient client, string verbe, string chemin, string? jeton = null)
    {
        using var requete = Requete(verbe, chemin, jeton);
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    [Fact]
    public async Task Au_dela_de_la_limite_globale_429_RetryAfter_ProblemDetails()
    {
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "2"));
        using var client = usine.CreateClient();
        var jeton = Creer(AudienceUnderwriting, ["Gestionnaire"]);

        await Envoyer(client, "GET", "/api/contrats", jeton);
        await Envoyer(client, "GET", "/api/contrats", jeton);
        var reponse = await Envoyer(client, "GET", "/api/contrats", jeton);

        Assert.Equal(HttpStatusCode.TooManyRequests, reponse.StatusCode);
        Assert.Equal("TROP_DE_REQUETES", await AutorisationTests.Code(reponse));
        Assert.True(reponse.Headers.RetryAfter?.Delta > TimeSpan.Zero, "Retry-After absent");
        Assert.Equal(2, backends.Underwriting.LogEntries.Count);
    }

    [Fact]
    public async Task Limite_par_utilisateur()
    {
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "1"));
        using var client = usine.CreateClient();

        await Envoyer(client, "GET", "/api/contrats", Creer(AudienceUnderwriting, ["Gestionnaire"], oid: "oid-a"));
        var encoreA = await Envoyer(client, "GET", "/api/contrats", Creer(AudienceUnderwriting, ["Gestionnaire"], oid: "oid-a"));
        var b = await Envoyer(client, "GET", "/api/contrats", Creer(AudienceUnderwriting, ["Gestionnaire"], oid: "oid-b"));

        Assert.Equal(HttpStatusCode.TooManyRequests, encoreA.StatusCode);
        Assert.Equal(HttpStatusCode.OK, b.StatusCode);
    }

    [Fact]
    public async Task Reponses_limite_plus_stricte()
    {
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "5"), ("RateLimit:Reponses:PermitLimit", "1"));
        using var client = usine.CreateClient();
        var jeton = Creer(AudienceRag, ["Gestionnaire"]);

        await Envoyer(client, "POST", "/api/reponses", jeton);
        var deuxieme = await Envoyer(client, "POST", "/api/reponses", jeton);
        var extraits = await Envoyer(client, "GET", "/api/extraits?question=bonus", jeton);

        Assert.Equal(HttpStatusCode.TooManyRequests, deuxieme.StatusCode);
        Assert.Equal(HttpStatusCode.OK, extraits.StatusCode);
    }

    [Fact]
    public async Task Sante_jamais_limitee()
    {
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "1"));
        using var client = usine.CreateClient();

        for (var i = 0; i < 5; i++)
        {
            Assert.Equal(HttpStatusCode.OK, (await Envoyer(client, "GET", "/health")).StatusCode);
            Assert.Equal(HttpStatusCode.OK, (await Envoyer(client, "GET", "/health/rag")).StatusCode);
            Assert.Equal(HttpStatusCode.OK, (await Envoyer(client, "GET", "/health/underwriting")).StatusCode);
        }
    }

    [Fact]
    public async Task Sans_jeton_partition_par_ip()
    {
        using var usine = backends.Gateway(("RateLimit:Global:PermitLimit", "1"));
        using var client = usine.CreateClient();

        await Envoyer(client, "GET", "/rag/openapi.json");
        var deuxieme = await Envoyer(client, "GET", "/rag/openapi.json");

        Assert.Equal(HttpStatusCode.TooManyRequests, deuxieme.StatusCode);
    }
}
