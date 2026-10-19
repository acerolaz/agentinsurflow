// Gateway AgentInsurFlow : seule entrée publique de la solution (S3-18).
// Routage déclaré dans appsettings.Routes.json ; jeton Entra validé et rôle exigé par route (S3-25).
// Première barrière seulement : chaque service revalide le jeton qu'on lui transmet tel quel.
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Extensions.Configuration.Json;
using OpenTelemetry.Exporter;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);
// Routes en PREMIÈRE source (la moins prioritaire) : variables d'environnement et réglages
// (ex. ReverseProxy__Clusters__rag__Destinations__d1__Address) gardent le dernier mot.
builder.Configuration.Sources.Insert(0, new JsonConfigurationSource
{
    Path = "appsettings.Routes.json",
    Optional = false,
    ReloadOnChange = true,
});

builder.Services.AddReverseProxy().LoadFromConfig(builder.Configuration.GetSection("ReverseProxy"));
builder.Services.AddOpenApi();

// Entra ID (S3-25) : sans tenant ni audiences, la gateway refuse de démarrer plutôt que de s'ouvrir.
var tenant = builder.Configuration["Entra:TenantId"]
    ?? throw new InvalidOperationException("Entra:TenantId manquant");
string[] Audiences(string service) =>
    builder.Configuration.GetSection($"Entra:Audiences:{service}").Get<string[]>() is { Length: > 0 } a
        ? a
        : throw new InvalidOperationException($"Entra:Audiences:{service} manquant");
var audiencesRag = Audiences("rag");
var audiencesUnderwriting = Audiences("underwriting");

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        o.Authority = $"https://login.microsoftonline.com/{tenant}/v2.0";
        o.MapInboundClaims = false;
        o.TokenValidationParameters.ValidIssuers =
            [$"https://login.microsoftonline.com/{tenant}/v2.0", $"https://sts.windows.net/{tenant}/"];
        o.TokenValidationParameters.ValidAudiences = [.. audiencesRag, .. audiencesUnderwriting];
        o.TokenValidationParameters.RoleClaimType = "roles";
        o.TokenValidationParameters.NameClaimType = "oid";
        o.Events = new JwtBearerEvents
        {
            OnChallenge = ctx =>
            {
                ctx.HandleResponse();
                ctx.Response.Headers.WWWAuthenticate = "Bearer";
                return Probleme(401, "Jeton absent ou invalide", "NON_AUTHENTIFIE").ExecuteAsync(ctx.HttpContext);
            },
            OnForbidden = ctx => Probleme(403, "Rôle ou audience insuffisant pour cette route", "ACCES_REFUSE").ExecuteAsync(ctx.HttpContext),
        };
    });

// Une politique = un rôle d'app ET l'audience du service visé (un jeton rag n'ouvre pas underwriting).
// Repli : tout ce qui ne déclare rien exige au moins un jeton valide (refus par défaut).
builder.Services.AddAuthorizationBuilder()
    .AddPolicy("rag-gestionnaire", p => p.RequireRole("Gestionnaire").RequireClaim("aud", audiencesRag))
    .AddPolicy("rag-ingestion", p => p.RequireRole("Ingestion").RequireClaim("aud", audiencesRag))
    .AddPolicy("underwriting-gestionnaire", p => p.RequireRole("Gestionnaire").RequireClaim("aud", audiencesUnderwriting))
    .AddPolicy("underwriting-telemetrie", p => p.RequireRole("Telemetrie").RequireClaim("aud", audiencesUnderwriting))
    .SetFallbackPolicy(new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build());

// Traces OTLP vers le référentiel SQL d'underwriting-admin (même réplique, localhost : S3-21)
var otlp = builder.Configuration["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] ?? "http://localhost:8002/v1/traces";
builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService(
        "agentinsurflow-gateway", serviceVersion: builder.Configuration["APP_VERSION"] ?? "dev"))
    .WithTracing(t => t
        .AddAspNetCoreInstrumentation(o => o.Filter = ctx => !ctx.Request.Path.StartsWithSegments("/health"))
        .AddHttpClientInstrumentation()
        .AddOtlpExporter(o =>
        {
            o.Endpoint = new Uri(otlp);
            o.Protocol = OtlpExportProtocol.HttpProtobuf;
        }));

var app = builder.Build();

// Page Swagger unique, à la racine : les 3 documents OpenAPI de la solution (S3-24).
// Connexion Entra en PKCE avec un seul client public (l'application agentinsurflow-rag).
// Placée avant l'authentification : la page est publique, les appels qu'elle fait portent le jeton.
app.UseSwaggerUI(ui =>
{
    ui.RoutePrefix = "";
    ui.DocumentTitle = "AgentInsurFlow — API";
    ui.SwaggerEndpoint("/rag/openapi.json", "rag");
    ui.SwaggerEndpoint("/underwriting/openapi/v1.json", "underwriting-admin");
    ui.SwaggerEndpoint("/openapi/v1.json", "gateway");
    ui.OAuthClientId(app.Configuration["SWAGGER_CLIENT_ID"] ?? "");
    ui.OAuthUsePkce();
});

app.UseAuthentication();
app.UseAuthorization();

app.MapGet("/health", (IConfiguration cfg) =>
        new Sante("ok", cfg["APP_VERSION"] ?? "dev", cfg["APP_RELEASE"] ?? "dev"))
    .WithName("SanteGateway")
    .WithSummary("Santé de la gateway (versions servies)")
    .AllowAnonymous();
app.MapOpenApi().AllowAnonymous(); // /openapi/v1.json

app.MapReverseProxy();

await app.RunAsync();

static IResult Probleme(int statut, string titre, string code) =>
    Results.Problem(statusCode: statut, title: titre, extensions: new Dictionary<string, object?> { ["code"] = code });

/// <summary>Santé de la gateway seule ; celle des services passe par <c>/health/rag</c> et <c>/health/underwriting</c>.</summary>
internal sealed record Sante(string Statut, string Version, string Release);

/// <summary>Point d'entrée, visible des tests (<c>WebApplicationFactory&lt;Program&gt;</c>).</summary>
public partial class Program;
