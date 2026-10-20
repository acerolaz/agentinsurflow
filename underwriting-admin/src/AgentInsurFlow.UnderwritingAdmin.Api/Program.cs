// underwriting-admin AgentInsurFlow : dossiers de souscription et référentiel SQL des traces (S3-21).
// Le jeton Entra est revalidé ici même s'il l'a déjà été par la gateway (défense en profondeur).
using System.Text.Json;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Identity.Web;
using Microsoft.OpenApi;
using OpenTelemetry.Exporter;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);

// JSON en snake_case pour toute l'API : les clients (rag) lisent ces noms tels quels.
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower);

// Entra ID : AzureAd:* lu dans la configuration, audience de ce service uniquement.
builder.Services.AddMicrosoftIdentityWebApiAuthentication(builder.Configuration);
builder.Services.Configure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
{
    o.TokenValidationParameters.RoleClaimType = "roles";
    o.TokenValidationParameters.NameClaimType = "oid";
    var evenements = o.Events ??= new JwtBearerEvents();
    evenements.OnChallenge = ctx =>
    {
        ctx.HandleResponse();
        ctx.Response.Headers.WWWAuthenticate = "Bearer";
        return Probleme(401, "Jeton absent ou invalide", "NON_AUTHENTIFIE").ExecuteAsync(ctx.HttpContext);
    };
    evenements.OnForbidden = ctx => Probleme(403, "Rôle insuffisant pour cette route", "ACCES_REFUSE").ExecuteAsync(ctx.HttpContext);
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

app.UseForwardedHeaders();
app.UseAuthentication();
app.UseAuthorization();

app.MapGet("/health", (IConfiguration cfg) =>
        new Sante("ok", cfg["APP_VERSION"] ?? "dev", cfg["APP_RELEASE"] ?? "dev"))
    .WithName("SanteUnderwritingAdmin")
    .WithSummary("Santé du service (versions servies)")
    .AllowAnonymous();
app.MapOpenApi().AllowAnonymous(); // /openapi/v1.json

await app.RunAsync();

static IResult Probleme(int statut, string titre, string code) =>
    Results.Problem(statusCode: statut, title: titre, extensions: new Dictionary<string, object?> { ["code"] = code });

/// <summary>Santé du service ; la gateway l'expose en <c>/health/underwriting</c>.</summary>
internal sealed record Sante(string Statut, string Version, string Release);

/// <summary>Point d'entrée, visible des tests (<c>WebApplicationFactory&lt;Program&gt;</c>).</summary>
public partial class Program;
