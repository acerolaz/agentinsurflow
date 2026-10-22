using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Protocols;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.IdentityModel.Tokens;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// Faux tenant Entra : une clé RSA de test signe les jetons, et la gateway la reçoit à la place
/// des métadonnées OIDC. Aucun appel réseau à login.microsoftonline.com.
/// </summary>
internal static class JetonsDeTest
{
    public const string Tenant = "00000000-0000-0000-0000-000000000001";
    public const string AudienceRag = "api://agentinsurflow-rag";
    public const string AudienceUnderwriting = "api://agentinsurflow-underwriting";
    public const string AudienceMcp = "api://agentinsurflow-mcp";
    public const string AudienceCalcul = "api://agentinsurflow-calcul";
    public static readonly string[] TousLesRoles = ["Gestionnaire", "Ingestion", "Telemetrie"];

    public static readonly string EmetteurV2 = $"https://login.microsoftonline.com/{Tenant}/v2.0";
    public static readonly string EmetteurV1 = $"https://sts.windows.net/{Tenant}/";

    public static readonly RsaSecurityKey Cle = NouvelleCle("cle-test");

    public static RsaSecurityKey NouvelleCle(string id) => new(RSA.Create(2048)) { KeyId = id };

    public static string Audience(string backend) => backend switch { "rag" => AudienceRag, "mcp" => AudienceMcp, _ => AudienceUnderwriting };

    public static string Creer(
        string audience, string[] roles, string oid = "oid-a",
        string? emetteur = null, DateTime? expire = null, SecurityKey? cle = null)
    {
        var fin = expire ?? DateTime.UtcNow.AddMinutes(5);
        return new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor
        {
            Issuer = emetteur ?? EmetteurV2,
            Audience = audience,
            NotBefore = fin.AddMinutes(-30),
            IssuedAt = fin.AddMinutes(-30),
            Expires = fin,
            Claims = new Dictionary<string, object> { ["oid"] = oid, ["roles"] = roles },
            SigningCredentials = new SigningCredentials(cle ?? Cle, SecurityAlgorithms.RsaSha256),
        });
    }

    /// <summary>Réglages Entra de test + clé de test à la place des métadonnées du tenant.</summary>
    public static IWebHostBuilder AvecEntraDeTest(this IWebHostBuilder b) => b
        .UseSetting("Entra:TenantId", Tenant)
        .UseSetting("Entra:Audiences:rag:0", AudienceRag)
        .UseSetting("Entra:Audiences:underwriting:0", AudienceUnderwriting)
        .UseSetting("Entra:Audiences:mcp:0", AudienceMcp)
        .UseSetting("Entra:Audiences:calcul:0", AudienceCalcul)
        .ConfigureTestServices(s => s.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
        {
            var metadonnees = new OpenIdConnectConfiguration { Issuer = EmetteurV2 };
            metadonnees.SigningKeys.Add(Cle);
            o.Configuration = metadonnees;
            // Le gestionnaire créé depuis l'Authority primerait sur Configuration et irait sur le réseau
            o.ConfigurationManager = new StaticConfigurationManager<OpenIdConnectConfiguration>(metadonnees);
        }));

    public static HttpRequestMessage Requete(string verbe, string chemin, string? jeton = null)
    {
        var requete = new HttpRequestMessage(new HttpMethod(verbe), chemin);
        if (jeton is not null)
        {
            requete.Headers.Add("Authorization", $"Bearer {jeton}");
        }
        return requete;
    }
}
