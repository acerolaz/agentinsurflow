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

/// <summary>Vrais jetons signés par une clé de test, dont l'émetteur est neutralisé (aucun accès réseau à Entra).</summary>
internal static class JetonsDeTest
{
    private const string Tenant = "00000000-0000-0000-0000-000000000001";
    private static readonly RsaSecurityKey Cle = new(RSA.Create(2048)) { KeyId = "cle-test" };
    private static readonly string Emetteur = $"https://login.microsoftonline.com/{Tenant}/v2.0";

    public const string AudienceParDefaut = "api://agentinsurflow-underwriting";

    public static WebApplicationFactory<Program> Usine(Action<IWebHostBuilder>? plus = null) =>
        new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("AzureAd:TenantId", Tenant);
            b.ConfigureTestServices(s => s.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
            {
                var metadonnees = new OpenIdConnectConfiguration { Issuer = Emetteur };
                metadonnees.SigningKeys.Add(Cle);
                // Le validateur d'émetteur d'Identity.Web irait chercher les métadonnées du tenant sur le réseau
                o.TokenValidationParameters.IssuerValidator = null;
                o.TokenValidationParameters.ValidIssuer = Emetteur;
                o.Configuration = metadonnees;
                o.ConfigurationManager = new StaticConfigurationManager<OpenIdConnectConfiguration>(metadonnees);
            }));
            plus?.Invoke(b);
        });

    public static string Jeton(string audience, string oid, params string[] roles) =>
        new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor
        {
            Issuer = Emetteur,
            Audience = audience,
            Expires = DateTime.UtcNow.AddMinutes(5),
            Claims = new Dictionary<string, object> { ["oid"] = oid, ["roles"] = roles },
            SigningCredentials = new SigningCredentials(Cle, SecurityAlgorithms.RsaSha256),
        });
}
