using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Text;
using Azure;
using Azure.Core;
using Azure.Identity;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.AspNetCore.Hosting;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>TI de la route <c>/api/llm/*</c> : appelants (rôle <c>LLM</c>) vers Azure AI Foundry avec le jeton de la gateway.</summary>
public sealed class LlmTests(Backends backends) : IClassFixture<Backends>
{
    private const string Portee = "https://cognitiveservices.azure.com/.default";
    private const string JetonGateway = "jeton-de-la-gateway";
    private const string Chemin = "/api/llm/v1/chat/completions";

    private static string JetonLlm(string[]? roles = null, string? azp = "app-a", string audience = AudienceLlm) =>
        Creer(audience, roles ?? ["LLM"], azp: azp);

    private static async Task<HttpResponseMessage> Envoyer(HttpClient client, string? jeton)
    {
        using var requete = Requete("POST", Chemin, jeton);
        requete.Content = new StringContent("{}", Encoding.UTF8, "application/json");
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

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

    private WebApplicationFactory<Program> Gateway(FauxCredential credential, params (string, string)[] reglages) =>
        backends.Gateway([("Llm:Portee", Portee), .. reglages])
            .WithWebHostBuilder(b => b.ConfigureTestServices(s => s.AddSingleton<TokenCredential>(credential)));

    [Fact]
    public async Task Post_llm_arrive_en_openai_avec_le_jeton_de_la_gateway()
    {
        var credential = new FauxCredential();
        using var usine = Gateway(credential);
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, JetonLlm());

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var recu = Assert.Single(backends.Llm.LogEntries).RequestMessage!;
        Assert.Equal("/openai/v1/chat/completions", recu.Path);
        Assert.Equal($"Bearer {JetonGateway}", Assert.Single(recu.Headers!["Authorization"]));
        Assert.Equal(Portee, Assert.Single(Assert.Single(credential.Portees)));
    }

    [Fact]
    public async Task Sans_jeton_401_sans_credential_ni_backend()
    {
        var credential = new FauxCredential();
        using var usine = Gateway(credential);
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, null);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        Assert.Equal("NON_AUTHENTIFIE", await AutorisationTests.Code(reponse));
        Assert.Empty(credential.Portees);
        Assert.Empty(backends.Llm.LogEntries);
    }

    [Fact]
    public async Task Sans_role_LLM_403()
    {
        using var usine = Gateway(new FauxCredential());
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, JetonLlm(["Gestionnaire"]));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Equal("ACCES_REFUSE", await AutorisationTests.Code(reponse));
        Assert.Empty(backends.Llm.LogEntries);
    }

    [Fact]
    public async Task Role_LLM_mauvaise_audience_403()
    {
        using var usine = Gateway(new FauxCredential());
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, JetonLlm(audience: AudienceMcp));

        Assert.Equal(HttpStatusCode.Forbidden, reponse.StatusCode);
        Assert.Empty(backends.Llm.LogEntries);
    }

    [Fact]
    public async Task Audience_GUID_acceptee()
    {
        const string guid = "22222222-2222-2222-2222-222222222222";
        using var usine = Gateway(new FauxCredential(), ("Entra:Audiences:llm:1", guid));
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, JetonLlm(audience: guid));

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Single(backends.Llm.LogEntries);
    }

    [Fact]
    public async Task Debit_par_azp_chaque_appelant_a_son_quota()
    {
        using var usine = Gateway(new FauxCredential(), ("RateLimit:Global:PermitLimit", "50"), ("RateLimit:Llm:PermitLimit", "1"));
        using var client = usine.CreateClient();

        // même oid, azp différents : deux quotas
        var a1 = await Envoyer(client, JetonLlm(azp: "app-a"));
        var a2 = await Envoyer(client, JetonLlm(azp: "app-a"));
        var b1 = await Envoyer(client, JetonLlm(azp: "app-b"));

        Assert.Equal(HttpStatusCode.OK, a1.StatusCode);
        Assert.Equal(HttpStatusCode.TooManyRequests, a2.StatusCode);
        Assert.Equal("TROP_DE_REQUETES", await AutorisationTests.Code(a2));
        Assert.Equal(HttpStatusCode.OK, b1.StatusCode);
    }

    [Fact]
    public async Task Credential_en_echec_502_LLM_INDISPONIBLE_sans_detail()
    {
        using var usine = Gateway(new FauxCredential(new AuthenticationFailedException("secret-interne")));
        using var client = usine.CreateClient();
        var jeton = JetonLlm();

        var reponse = await Envoyer(client, jeton);

        Assert.Equal(HttpStatusCode.BadGateway, reponse.StatusCode);
        Assert.Equal("LLM_INDISPONIBLE", await AutorisationTests.Code(reponse));
        var corps = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        Assert.DoesNotContain("secret-interne", corps, StringComparison.Ordinal);
        Assert.DoesNotContain(jeton, corps, StringComparison.Ordinal);
        Assert.Empty(backends.Llm.LogEntries);
    }

    [Fact]
    public async Task Reponse_en_flux_non_tamponnee()
    {
        var suite = new TaskCompletionSource();
        var constructeur = WebApplication.CreateSlimBuilder();
        constructeur.WebHost.UseUrls("http://127.0.0.1:0");
        await using var amont = constructeur.Build();
        amont.MapPost("/openai/v1/chat/completions", async (HttpContext ctx) =>
        {
            ctx.Response.ContentType = "text/event-stream";
            await ctx.Response.WriteAsync("data: un\n\n", ctx.RequestAborted);
            await ctx.Response.Body.FlushAsync(ctx.RequestAborted);
            await suite.Task.WaitAsync(ctx.RequestAborted);
            await ctx.Response.WriteAsync("data: deux\n\n", ctx.RequestAborted);
        });
        await amont.StartAsync(TestContext.Current.CancellationToken);
        var adresse = amont.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First();

        using var usine = Gateway(new FauxCredential(), ("ReverseProxy:Clusters:llm:Destinations:d1:Address", adresse));
        using var client = usine.CreateClient();
        using var requete = Requete("POST", Chemin, JetonLlm());
        requete.Content = new StringContent("{}", Encoding.UTF8, "application/json");

        using var reponse = await client.SendAsync(requete, HttpCompletionOption.ResponseHeadersRead, TestContext.Current.CancellationToken);
        using var flux = new StreamReader(await reponse.Content.ReadAsStreamAsync(TestContext.Current.CancellationToken));
        var premier = await flux.ReadLineAsync(TestContext.Current.CancellationToken).AsTask().WaitAsync(TimeSpan.FromSeconds(10), TestContext.Current.CancellationToken);

        Assert.Equal("data: un", premier); // reçu alors que l'amont n'a pas fini
        suite.SetResult();
    }

    /// <summary>Amont Foundry factice : répond <paramref name="corps"/> tel quel avec ce type de contenu.</summary>
    private static async Task<(WebApplication Amont, string Adresse)> AmontFixe(string type, string corps)
    {
        var constructeur = WebApplication.CreateSlimBuilder();
        constructeur.WebHost.UseUrls("http://127.0.0.1:0");
        var amont = constructeur.Build();
        amont.MapPost("/openai/v1/chat/completions", async (HttpContext ctx) =>
        {
            ctx.Response.ContentType = type;
            await ctx.Response.WriteAsync(corps, ctx.RequestAborted);
        });
        await amont.StartAsync(TestContext.Current.CancellationToken);
        return (amont, amont.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First());
    }

    /// <summary>Un appel avec ce jeton ; rend le corps reçu et les attributs du span serveur de la requête.</summary>
    private async Task<(string Corps, Dictionary<string, object?> Attributs)> AppelMesure(string type, string corps, string jeton, string azpAttendu)
    {
        var spans = new ConcurrentBag<Activity>();
        using var ecoute = new ActivityListener
        {
            ShouldListenTo = s => s.Name == "Microsoft.AspNetCore",
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = spans.Add,
        };
        ActivitySource.AddActivityListener(ecoute);
        var (amont, adresse) = await AmontFixe(type, corps);
        await using var _ = amont;
        using var usine = Gateway(new FauxCredential(), ("ReverseProxy:Clusters:llm:Destinations:d1:Address", adresse));
        using var client = usine.CreateClient();

        var reponse = await Envoyer(client, jeton);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        var recu = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        // listener global (tests en parallèle) : le span de CET appel, retrouvé par son appelant, unique par test
        var span = Assert.Single(spans, a => a.GetTagItem("appelant.azp") as string == azpAttendu);
        return (recu, span.TagObjects.ToDictionary(t => t.Key, t => t.Value));
    }

    private Task<(string Corps, Dictionary<string, object?> Attributs)> AppelMesure(string type, string corps, string azp) =>
        AppelMesure(type, corps, JetonLlm(azp: azp), azp);

    [Fact]
    public async Task Reponse_json_tokens_et_modele_dans_le_span_corps_identique()
    {
        const string corps = """{"model":"gpt-4o-mini","choices":[{"message":{"content":"texte-secret-reponse"}}],"usage":{"prompt_tokens":12,"completion_tokens":34}}""";

        var (recu, attributs) = await AppelMesure("application/json", corps, "app-mesure-json");

        Assert.Equal(corps, recu);
        Assert.Equal(12L, attributs["gen_ai.usage.input_tokens"]);
        Assert.Equal(34L, attributs["gen_ai.usage.output_tokens"]);
        Assert.Equal("gpt-4o-mini", attributs["gen_ai.response.model"]);
        Assert.DoesNotContain(attributs.Values, v => v?.ToString()?.Contains("texte-secret-reponse", StringComparison.Ordinal) == true);
        Assert.False(attributs.ContainsKey("gen_ai.usage.mesure"));
    }

    [Fact]
    public async Task Embeddings_sans_completion_seul_input_tokens()
    {
        const string corps = """{"model":"embed","data":[],"usage":{"prompt_tokens":7}}""";

        var (_, attributs) = await AppelMesure("application/json", corps, "app-mesure-embed");

        Assert.Equal(7L, attributs["gen_ai.usage.input_tokens"]);
        Assert.False(attributs.ContainsKey("gen_ai.usage.output_tokens"));
    }

    [Theory]
    [InlineData("pas du json {", "app-mesure-invalide")]
    [InlineData("""{"model":"m","choices":[]}""", "app-mesure-sans-usage")]
    public async Task Json_invalide_ou_sans_usage_aucun_nombre_et_corps_intact(string corps, string azp)
    {
        var (recu, attributs) = await AppelMesure("application/json", corps, azp);

        Assert.Equal(corps, recu);
        Assert.False(attributs.ContainsKey("gen_ai.usage.input_tokens"));
        Assert.False(attributs.ContainsKey("gen_ai.usage.output_tokens"));
    }

    [Fact]
    public async Task Flux_non_mesure_non_disponible_et_corps_intact()
    {
        const string corps = "data: {\"usage\":{\"prompt_tokens\":1}}\n\n";

        var (recu, attributs) = await AppelMesure("text/event-stream", corps, "app-mesure-flux");

        Assert.Equal(corps, recu);
        Assert.Equal("non_disponible", attributs["gen_ai.usage.mesure"]);
        Assert.False(attributs.ContainsKey("gen_ai.usage.input_tokens"));
    }

    [Fact]
    public async Task Sans_azp_ni_appid_repli_sur_oid()
    {
        var jeton = Creer(AudienceLlm, ["LLM"], oid: "oid-mesure-repli");

        var (_, attributs) = await AppelMesure("application/json", """{"usage":{"prompt_tokens":3}}""", jeton, "oid-mesure-repli");

        Assert.Equal(3L, attributs["gen_ai.usage.input_tokens"]);
    }

    [Fact]
    public void Sans_secret_ManagedIdentity_avec_secret_ClientSecretCredential()
    {
        using var sans = backends.Gateway();
        using var avec = backends.Gateway(("Gateway:ClientId", "client-gw"), ("Gateway:ClientSecret", "s3cret"));

        Assert.IsType<ManagedIdentityCredential>(sans.Services.GetRequiredService<TokenCredential>());
        Assert.IsType<ClientSecretCredential>(avec.Services.GetRequiredService<TokenCredential>());
    }
}
