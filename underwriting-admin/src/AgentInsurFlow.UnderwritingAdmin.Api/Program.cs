// underwriting-admin AgentInsurFlow : dossiers de souscription et référentiel SQL des traces (S3-21).
// Le jeton Entra est revalidé ici même s'il l'a déjà été par la gateway (défense en profondeur).
using System.Text.Json;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.HttpOverrides;
using AgentInsurFlow.UnderwritingAdmin.Api;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;
using Microsoft.Identity.Web;
using Microsoft.OpenApi;
using OpenTelemetry.Exporter;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);

// JSON en snake_case pour toute l'API : les clients (rag) lisent ces noms tels quels.
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower);

// Entra ID : AzureAd:* (tenant, client) lu dans la configuration. Audiences = convention de la gateway et de rag :
// Entra:Audiences:underwriting, chaque valeur pouvant être une liste « a, b » (UNDERWRITING_API_AUDIENCES).
var audiences = (builder.Configuration.GetSection("Entra:Audiences:underwriting").Get<string[]>() ?? [])
    .SelectMany(v => v.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
    .ToArray();
if (audiences.Length == 0)
{
    throw new InvalidOperationException("Entra:Audiences:underwriting manquant");
}
builder.Services.AddMicrosoftIdentityWebApiAuthentication(builder.Configuration);
// PostConfigure : passe après Identity.Web, qui fixerait sinon sa propre audience (ClientId).
builder.Services.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
{
    o.TokenValidationParameters.ValidAudience = null;
    o.TokenValidationParameters.AudienceValidator = null;
    o.TokenValidationParameters.ValidAudiences = audiences;
    // Claims gardés tels quels (« oid », « roles »), comme la gateway : sinon .NET les renomme et les rôles ne sont plus vus
    o.MapInboundClaims = false;
    o.TokenValidationParameters.RoleClaimType = "roles";
    o.TokenValidationParameters.NameClaimType = "oid";
    var evenements = o.Events ??= new JwtBearerEvents();
    evenements.OnChallenge = ctx =>
    {
        ctx.HandleResponse();
        ctx.Response.Headers.WWWAuthenticate = "Bearer";
        return Problemes.Creer(401, "Jeton absent ou invalide", "NON_AUTHENTIFIE").ExecuteAsync(ctx.HttpContext);
    };
    evenements.OnForbidden = ctx => Problemes.Creer(403, "Rôle insuffisant pour cette route", "ACCES_REFUSE").ExecuteAsync(ctx.HttpContext);
});

// Refus par défaut : tout ce qui ne déclare rien exige un utilisateur authentifié.
builder.Services.AddAuthorizationBuilder()
    .AddPolicy("Gestionnaire", p => p.RequireRole("Gestionnaire"))
    .AddPolicy("Telemetrie", p => p.RequireRole("Telemetrie"))
    .SetFallbackPolicy(new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build());

// Document OpenAPI sans `servers` (la page Swagger unique est celle de la gateway) mais avec le schéma Bearer.
builder.Services.AddOpenApi(o => o.AddDocumentTransformer((doc, _, _) =>
{
    doc.Servers = null;
    doc.Components ??= new OpenApiComponents();
    doc.Components.SecuritySchemes = new Dictionary<string, IOpenApiSecurityScheme>
    {
        ["Bearer"] = new OpenApiSecurityScheme { Type = SecuritySchemeType.Http, Scheme = "bearer", BearerFormat = "JWT" },
    };
    return Task.CompletedTask;
}));

// Seul le préfixe de la gateway (X-Forwarded-Prefix) est repris : X-Forwarded-For reste celui lu par la règle S3-21.
builder.Services.Configure<ForwardedHeadersOptions>(o =>
{
    o.ForwardedHeaders = ForwardedHeaders.XForwardedPrefix;
    o.KnownIPNetworks.Clear();
    o.KnownProxies.Clear();
});

// Base dossiers : routes en lecture seule (compte `dossiers`, vue minimisée) ; les migrations passent par `migrateur`.
var connexions = new ConnexionsDossiers(
    builder.Configuration["PG_HOST"] ?? "localhost",
    int.Parse(builder.Configuration["PG_PORT"] ?? "5432", System.Globalization.CultureInfo.InvariantCulture),
    builder.Configuration["PG_SUFFIXE_BASES"] ?? "",
    builder.Configuration["PG_MIGRATEUR_PASSWORD"],
    builder.Configuration["PG_DOSSIERS_PASSWORD"] ?? "");
builder.Services.AjouterDossiers(connexions);
builder.Services.AddScoped<ListerPortefeuille>().AddScoped<ConsulterContrat>();

// Les spans de ce service rejoignent leur propre référentiel, par son /v1/traces en localhost.
var otlp = builder.Configuration["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] ?? "http://localhost:8002/v1/traces";
builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService(
        "agentinsurflow-underwriting", serviceVersion: builder.Configuration["APP_VERSION"] ?? "dev"))
    .WithTracing(t => t
        .AddAspNetCoreInstrumentation(o => o.Filter = ctx => !ctx.Request.Path.StartsWithSegments("/health")
            && !ctx.Request.Path.StartsWithSegments("/v1/traces")) // pas de boucle : l'export lui-même n'est pas tracé
        .AddHttpClientInstrumentation()
        .AddOtlpExporter(o =>
        {
            o.Endpoint = new Uri(otlp);
            o.Protocol = OtlpExportProtocol.HttpProtobuf;
        }));

var app = builder.Build();

// Schéma et seed au démarrage (compte migrateur), après attente de PostgreSQL : Migrations:AuDemarrage=true.
if (builder.Configuration.GetValue<bool>("Migrations:AuDemarrage"))
{
    await MigrationsDossiers.AppliquerAsync(connexions, TimeSpan.FromSeconds(60), CancellationToken.None);
}

app.UseForwardedHeaders();
app.UseAuthentication();
app.UseAuthorization();

app.MapGet("/health", (IConfiguration cfg) =>
        new Sante("ok", cfg["APP_VERSION"] ?? "dev", cfg["APP_RELEASE"] ?? "dev"))
    .WithName("SanteUnderwritingAdmin")
    .WithSummary("Santé du service (versions servies)")
    .AllowAnonymous();
app.MapContrats();
app.MapOpenApi().AllowAnonymous(); // /openapi/v1.json

await app.RunAsync();

/// <summary>Santé du service ; la gateway l'expose en <c>/health/underwriting</c>.</summary>
internal sealed record Sante(string Statut, string Version, string Release);

/// <summary>Point d'entrée, visible des tests (<c>WebApplicationFactory&lt;Program&gt;</c>).</summary>
public partial class Program;
