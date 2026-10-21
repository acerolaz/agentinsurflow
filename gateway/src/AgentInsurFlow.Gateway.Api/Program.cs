// Gateway AgentInsurFlow : seule entrée publique de la solution (S3-18).
// Routage déclaré dans appsettings.Routes.json ; jeton Entra validé et rôle exigé par route (S3-25).
// Première barrière seulement : chaque service revalide le jeton qu'on lui transmet tel quel.
using System.Globalization;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.HttpOverrides;
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
// Chaque valeur peut être une liste « a, b » : la même variable que le service (RAG_API_AUDIENCES).
string[] Audiences(string service) =>
    (builder.Configuration.GetSection($"Entra:Audiences:{service}").Get<string[]>() ?? [])
        .SelectMany(v => v.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
        .ToArray() is { Length: > 0 } a
        ? a
        : throw new InvalidOperationException($"Entra:Audiences:{service} manquant");
var audiencesRag = Audiences("rag");
var audiencesUnderwriting = Audiences("underwriting");
var audiencesMcp = Audiences("mcp");

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        o.Authority = $"https://login.microsoftonline.com/{tenant}/v2.0";
        o.MapInboundClaims = false;
        o.TokenValidationParameters.ValidIssuers =
            [$"https://login.microsoftonline.com/{tenant}/v2.0", $"https://sts.windows.net/{tenant}/"];
        o.TokenValidationParameters.ValidAudiences = [.. audiencesRag, .. audiencesUnderwriting, .. audiencesMcp];
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
    .AddPolicy("mcp-gestionnaire", p => p.RequireRole("Gestionnaire").RequireClaim("aud", audiencesMcp))
    .AddPolicy("underwriting-telemetrie", p => p.RequireRole("Telemetrie").RequireClaim("aud", audiencesUnderwriting))
    .SetFallbackPolicy(new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build());

// IP réelle du client (S3-26) : en Azure, l'envoy de Container Apps ajoute l'IP du client à la fin
// de X-Forwarded-For ; seule cette dernière entrée est reprise. Éteint en local, où la gateway est
// joignable directement et où cet en-tête viendrait du client lui-même.
var envoyDevant = builder.Configuration.GetValue<bool>("Proxy:EnvoyDevant");
builder.Services.Configure<ForwardedHeadersOptions>(o =>
{
    o.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    o.ForwardLimit = 1;
    o.KnownIPNetworks.Clear(); // l'entrée externe ne passe que par l'envoy, dont l'IP interne varie
    o.KnownProxies.Clear();
});

// Limitation de débit (S3-27) : fenêtre fixe par utilisateur (oid), sinon par IP.
// ponytail: compteurs en mémoire par réplique (maxReplicas = 1) ; stockage partagé si on passe à plusieurs répliques.
var fenetre = TimeSpan.FromSeconds(builder.Configuration.GetValue("RateLimit:FenetreSecondes", 60));
int Limite(string nom, int defaut) => builder.Configuration.GetValue($"RateLimit:{nom}:PermitLimit", defaut);
var limiteGlobale = Limite("Global", 120);
var limiteReponses = Limite("Reponses", 10);
var limiteMcp = Limite("Mcp", 60);
builder.Services.AddRateLimiter(o =>
{
    o.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(ctx =>
        RateLimitPartition.GetFixedWindowLimiter(Partition(ctx), _ => FenetreFixe(limiteGlobale, fenetre)));
    o.AddPolicy("reponses", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(Partition(ctx), _ => FenetreFixe(limiteReponses, fenetre)));
    o.AddPolicy("mcp", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(Partition(ctx), _ => FenetreFixe(limiteMcp, fenetre)));
    o.OnRejected = (ctx, _) =>
    {
        if (ctx.Lease.TryGetMetadata(MetadataName.RetryAfter, out var attente))
        {
            ctx.HttpContext.Response.Headers.RetryAfter =
                ((int)Math.Ceiling(attente.TotalSeconds)).ToString(CultureInfo.InvariantCulture);
        }
        return new ValueTask(Probleme(429, "Trop de requêtes, réessayez plus tard", "TROP_DE_REQUETES").ExecuteAsync(ctx.HttpContext));
    };
});

// Traces OTLP vers le référentiel SQL d'underwriting-admin (même réplique, localhost : S3-21)
var otlp = builder.Configuration["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] ?? "http://localhost:8002/v1/traces";
builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService(
        "agentinsurflow-gateway", serviceVersion: builder.Configuration["APP_VERSION"] ?? "dev"))
    .WithTracing(t => t
        .AddAspNetCoreInstrumentation(o =>
        {
            o.Filter = ctx => !ctx.Request.Path.StartsWithSegments("/health");
            // client.address (S3-26) : l'instrumentation ne le pose pas ; lu en fin de requête, donc après
            // UseForwardedHeaders : l'IP réelle derrière l'envoy, pas celle de l'envoy
            o.EnrichWithHttpResponse = (activite, reponse) =>
                activite.SetTag("client.address", reponse.HttpContext.Connection.RemoteIpAddress?.ToString());
        })
        .AddHttpClientInstrumentation()
        .AddOtlpExporter(o =>
        {
            o.Endpoint = new Uri(otlp);
            o.Protocol = OtlpExportProtocol.HttpProtobuf;
        }));

var app = builder.Build();

if (envoyDevant)
{
    app.UseForwardedHeaders();
}

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

// Débit après l'authentification (partition par oid), avant l'autorisation (les refus comptent aussi)
app.UseAuthentication();
app.UseRateLimiter();
app.UseAuthorization();

app.MapGet("/health", (IConfiguration cfg) =>
        new Sante("ok", cfg["APP_VERSION"] ?? "dev", cfg["APP_RELEASE"] ?? "dev"))
    .WithName("SanteGateway")
    .WithSummary("Santé de la gateway (versions servies)")
    .AllowAnonymous()
    .DisableRateLimiting(); // sondes de Container Apps
app.MapOpenApi().AllowAnonymous(); // /openapi/v1.json

app.MapReverseProxy();

await app.RunAsync();

static IResult Probleme(int statut, string titre, string code) =>
    Results.Problem(statusCode: statut, title: titre, extensions: new Dictionary<string, object?> { ["code"] = code });

static string Partition(HttpContext ctx) =>
    ctx.User.FindFirst("oid")?.Value is { } oid ? $"oid:{oid}" : $"ip:{ctx.Connection.RemoteIpAddress}";

static FixedWindowRateLimiterOptions FenetreFixe(int limite, TimeSpan fenetre) =>
    new() { PermitLimit = limite, Window = fenetre, QueueLimit = 0 };

/// <summary>Santé de la gateway seule ; celle des services passe par <c>/health/rag</c> et <c>/health/underwriting</c>.</summary>
internal sealed record Sante(string Statut, string Version, string Release);

/// <summary>Point d'entrée, visible des tests (<c>WebApplicationFactory&lt;Program&gt;</c>).</summary>
public partial class Program;
