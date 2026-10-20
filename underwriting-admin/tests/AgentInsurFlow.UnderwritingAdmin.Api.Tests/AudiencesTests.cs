using System.Net;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Protocols;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.IdentityModel.Tokens;

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>TI : la liste « a, b » d'audiences (convention gateway/rag) est découpée, chaque valeur est acceptée.</summary>
public sealed class AudiencesTests : IDisposable
{
    private const string Tenant = "00000000-0000-0000-0000-000000000001";
    private static readonly RsaSecurityKey Cle = new(RSA.Create(2048)) { KeyId = "cle-test" };
    private static readonly string[] RolesGestionnaire = ["Gestionnaire"];
    private static readonly string Emetteur = $"https://login.microsoftonline.com/{Tenant}/v2.0";

    private readonly WebApplicationFactory<Program> _usine = new WebApplicationFactory<Program>().WithWebHostBuilder(b => b
        .UseSetting("AzureAd:TenantId", Tenant)
        .UseSetting("Entra:Audiences:underwriting:0", "api://a, api://b")
        .ConfigureTestServices(s => s.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
        {
            var metadonnees = new OpenIdConnectConfiguration { Issuer = Emetteur };
            metadonnees.SigningKeys.Add(Cle);
            // Le validateur d'émetteur d'Identity.Web irait chercher les métadonnées du tenant sur le réseau
            o.TokenValidationParameters.IssuerValidator = null;
            o.TokenValidationParameters.ValidIssuer = Emetteur;
            o.Configuration = metadonnees;
            o.ConfigurationManager = new StaticConfigurationManager<OpenIdConnectConfiguration>(metadonnees);
        })));

    public void Dispose() => _usine.Dispose();

    private async Task<HttpStatusCode> Appeler(string audience)
    {
        var jeton = new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor
        {
            Issuer = Emetteur,
            Audience = audience,
            Expires = DateTime.UtcNow.AddMinutes(5),
            Claims = new Dictionary<string, object> { ["oid"] = "oid-a", ["roles"] = RolesGestionnaire },
            SigningCredentials = new SigningCredentials(Cle, SecurityAlgorithms.RsaSha256),
        });
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, "/api/inconnue");
        requete.Headers.Add("Authorization", $"Bearer {jeton}");
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        return reponse.StatusCode;
    }

    // Jeton valide : le repli exige seulement un utilisateur authentifié, la route inconnue répond donc 404.
    [Theory]
    [InlineData("api://a")]
    [InlineData("api://b")]
    public async Task Jeton_de_chaque_audience_de_la_liste_est_accepte(string audience) =>
        Assert.Equal(HttpStatusCode.NotFound, await Appeler(audience));

    [Fact]
    public async Task Jeton_d_une_autre_audience_401() =>
        Assert.Equal(HttpStatusCode.Unauthorized, await Appeler("api://c"));
}
