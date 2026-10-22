using System.Net;
using Azure.Core;
using Azure.Identity;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>TU du handler qui pose le jeton d'application sur l'export OTLP de la gateway vers underwriting-admin.</summary>
public sealed class JetonOtlpHandlerTests
{
    private const string Portee = "api://underwriting/.default";

    private sealed class FauxCredential(Exception? echec = null) : TokenCredential
    {
        public List<string[]> Portees { get; } = [];

        public override AccessToken GetToken(TokenRequestContext c, CancellationToken ct)
        {
            Portees.Add(c.Scopes);
            return echec is null ? new AccessToken("jeton-otlp", DateTimeOffset.UtcNow.AddHours(1)) : throw echec;
        }

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext c, CancellationToken ct) => new(GetToken(c, ct));
    }

    private sealed class Amont : HttpMessageHandler
    {
        public HttpRequestMessage? Recue { get; private set; }

        protected override HttpResponseMessage Send(HttpRequestMessage r, CancellationToken ct) => Repondre(r);

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r, CancellationToken ct) => Task.FromResult(Repondre(r));

        private HttpResponseMessage Repondre(HttpRequestMessage r)
        {
            Recue = r;
            return new HttpResponseMessage(HttpStatusCode.OK);
        }
    }

    private static (HttpMessageInvoker, Amont) Chaine(string? portee, FauxCredential credential)
    {
        var amont = new Amont();
        return (new HttpMessageInvoker(new JetonOtlpHandler(() => credential, portee) { InnerHandler = amont }), amont);
    }

    [Fact]
    public void Envoi_synchrone_pose_le_jeton_avec_la_portee_configuree()
    {
        var credential = new FauxCredential();
        var (client, amont) = Chaine(Portee, credential);

        using var reponse = client.Send(new HttpRequestMessage(HttpMethod.Post, "http://x/v1/traces"), TestContext.Current.CancellationToken);

        Assert.Equal("Bearer jeton-otlp", amont.Recue!.Headers.Authorization!.ToString());
        Assert.Equal(Portee, Assert.Single(Assert.Single(credential.Portees)));
    }

    [Fact]
    public async Task Envoi_asynchrone_pose_le_jeton()
    {
        var (client, amont) = Chaine(Portee, new FauxCredential());

        using var reponse = await client.SendAsync(new HttpRequestMessage(HttpMethod.Post, "http://x/v1/traces"), TestContext.Current.CancellationToken);

        Assert.Equal("Bearer jeton-otlp", amont.Recue!.Headers.Authorization!.ToString());
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public void Sans_audience_aucun_en_tete_et_aucun_appel_au_credential(string? portee)
    {
        var credential = new FauxCredential();
        var (client, amont) = Chaine(portee, credential);

        using var reponse = client.Send(new HttpRequestMessage(HttpMethod.Post, "http://x/v1/traces"), TestContext.Current.CancellationToken);

        Assert.Null(amont.Recue!.Headers.Authorization);
        Assert.Empty(credential.Portees);
    }

    [Fact]
    public async Task Echec_du_credential_part_sans_jeton_et_sans_exception()
    {
        var (client, amont) = Chaine(Portee, new FauxCredential(new CredentialUnavailableException("detail-ne-doit-pas-fuiter")));

        using var reponse = await client.SendAsync(new HttpRequestMessage(HttpMethod.Post, "http://x/v1/traces"), TestContext.Current.CancellationToken);

        Assert.Null(amont.Recue!.Headers.Authorization);
        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode); // l'amont décide (401 en vrai) : l'export n'est jamais bloqué
    }
}
