// Gateway AgentInsurFlow : seule entrée publique de la solution (S3-18).
// Routage déclaré dans appsettings.Routes.json ; jeton Entra validé et rôle exigé par route (S3-25).
// Première barrière seulement : chaque service revalide le jeton qu'on lui transmet tel quel.
using System.Globalization;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Threading.RateLimiting;
using Azure;
using Azure.Core;
using Azure.Identity;
using Azure.Monitor.OpenTelemetry.AspNetCore;
using AgentInsurFlow.Gateway.Api;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Extensions.Configuration.Json;
using Microsoft.Extensions.FileProviders;
using OpenTelemetry.Exporter;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Yarp.ReverseProxy.Transforms;

var builder = WebApplication.CreateBuilder(args);
// Routes en PREMIÈRE source (la moins prioritaire) : variables d'environnement et réglages
// (ex. ReverseProxy__Clusters__rag__Destinations__d1__Address) gardent le dernier mot.
builder.Configuration.Sources.Insert(0, new JsonConfigurationSource
{
    Path = "appsettings.Routes.json",
    Optional = false,
    ReloadOnChange = true,
});

// Échange de jeton (route calcul seulement) : la Function n'accepte que le jeton de la gateway (identité
// managée), jamais celui du MCP. Source injectable (TokenCredential) pour que les tests la remplacent.
// Route -> (portée, code d'erreur) ; une portée vide (local) désactive le jeton relayé.
var echanges = new Dictionary<string, (string? Portee, string Code, string Titre)>
{
    ["calcul"] = (builder.Configuration["Calcul:Portee"], "CALCUL_INDISPONIBLE", "Service de calcul indisponible"),
    ["llm"] = (builder.Configuration["Llm:Portee"], "LLM_INDISPONIBLE", "Service LLM indisponible"),
};
// Local : secret d'application de la gateway ; Azure : identité managée.
builder.Services.AddSingleton<TokenCredential>(_ =>
    builder.Configuration["Gateway:ClientSecret"] is { Length: > 0 } secret
        ? new ClientSecretCredential(builder.Configuration["Entra:TenantId"], builder.Configuration["Gateway:ClientId"], secret)
        : builder.Configuration["Calcul:IdentiteClientId"] is { Length: > 0 } id
            ? new ManagedIdentityCredential(ManagedIdentityId.FromUserAssignedClientId(id))
            : new ManagedIdentityCredential(ManagedIdentityId.SystemAssigned));
builder.Services.AddReverseProxy()
    .LoadFromConfig(builder.Configuration.GetSection("ReverseProxy"))
    .AddTransforms(ctx =>
    {
        if (ctx.Route.RouteId == "llm")
        {
            // Mesure des tokens (#70) : attributs du span serveur, jamais de texte. Le corps relayé reste identique.
            ctx.AddRequestTransform(t =>
            {
                t.ProxyRequest.Headers.AcceptEncoding.Clear(); // amont non compressé : le JSON reste lisible
                return default;
            });
            ctx.AddResponseTransform(async t => await MesurerTokens(t.HttpContext, t.ProxyResponse));
        }
        if (!echanges.TryGetValue(ctx.Route.RouteId, out var echange))
        {
            return;
        }
        var (portee, code, titre) = echange;
        ctx.AddRequestTransform(async t =>
        {
            t.ProxyRequest.Headers.Authorization = null;
            if (string.IsNullOrEmpty(portee))
            {
                return; // local : aucun jeton relayé
            }
            try
            {
                var credential = t.HttpContext.RequestServices.GetRequiredService<TokenCredential>();
                var jeton = await credential.GetTokenAsync(new TokenRequestContext([portee]), t.HttpContext.RequestAborted);
                t.ProxyRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", jeton.Token);
            }
            catch (Exception e) when (e is AuthenticationFailedException or RequestFailedException or HttpRequestException) // jamais de détail ni de jeton dans la réponse ou le journal
            {
                await Probleme(502, titre, code).ExecuteAsync(t.HttpContext);
            }
        });
    });
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
var audiencesCalcul = Audiences("calcul");
var audiencesLlm = Audiences("llm");
var audiencesCluster = Audiences("cluster");
// Client id du serveur MCP (azp de ses jetons OBO) : seul appelant de PUT /api/contrats/{n}/etat. Vide : route fermée.
var clientMcp = builder.Configuration["Entra:McpClientId"];

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        o.Authority = $"https://login.microsoftonline.com/{tenant}/v2.0";
        o.MapInboundClaims = false;
        o.TokenValidationParameters.ValidIssuers =
            [$"https://login.microsoftonline.com/{tenant}/v2.0", $"https://sts.windows.net/{tenant}/"];
        o.TokenValidationParameters.ValidAudiences = [.. audiencesRag, .. audiencesUnderwriting, .. audiencesMcp, .. audiencesCalcul, .. audiencesLlm, .. audiencesCluster];
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
    .AddPolicy("cluster-gestionnaire", p => p.RequireRole("Gestionnaire").RequireClaim("aud", audiencesCluster)) // jeton relayé tel quel (R18) : le cluster le revalide
    .AddPolicy("calcul-mcp", p => p.RequireRole("Calcul").RequireClaim("aud", audiencesCalcul)) // jeton MCP entrant, remplacé par celui de la gateway
    .AddPolicy("llm-appelant", p => p.RequireRole("LLM").RequireClaim("aud", audiencesLlm)) // jeton de l'appelant, remplacé par celui de la gateway
    .AddPolicy("underwriting-etat-mcp", p => p.RequireRole("Gestionnaire").RequireClaim("aud", audiencesUnderwriting) // mémoire du dossier (D100) : écrite par le MCP, pas par un client direct
        .RequireAssertion(ctx => !string.IsNullOrEmpty(clientMcp) && ctx.User.FindFirst("azp")?.Value == clientMcp))
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
var limiteCalcul = Limite("Calcul", 60);
var limiteLlm = Limite("Llm", 30);
var limiteCluster = Limite("Cluster", 10); // une évaluation = plusieurs appels LLM : comme /api/reponses
builder.Services.AddRateLimiter(o =>
{
    o.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(ctx =>
        RateLimitPartition.GetFixedWindowLimiter(Partition(ctx), _ => FenetreFixe(limiteGlobale, fenetre)));
    o.AddPolicy("reponses", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(Partition(ctx), _ => FenetreFixe(limiteReponses, fenetre)));
    o.AddPolicy("mcp", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(Partition(ctx), _ => FenetreFixe(limiteMcp, fenetre)));
    o.AddPolicy("cluster", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(Partition(ctx), _ => FenetreFixe(limiteCluster, fenetre)));
    o.AddPolicy("calcul", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(Partition(ctx), _ => FenetreFixe(limiteCalcul, fenetre)));
    o.AddPolicy("llm", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(PartitionAppelant(ctx), _ => FenetreFixe(limiteLlm, fenetre)));
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

// Traces OTLP vers le référentiel SQL d'underwriting-admin (sa Container App, adresse interne) avec un jeton
// d'application (rôle Telemetrie, audience Telemetrie:Audience) ; sans audience (local, compose) : sans jeton (S3-21).
var otlp = builder.Configuration["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] ?? "http://localhost:8002/v1/traces";
var audienceTelemetrie = builder.Configuration["Telemetrie:Audience"];
IServiceProvider? fournisseur = null; // posé après Build : l'exporteur n'est créé qu'au démarrage de l'hôte
builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService(
        "agentinsurflow-gateway", serviceVersion: builder.Configuration["APP_VERSION"] ?? "dev"))
    .WithTracing(t => t
        .AddProcessor(new MasquageNumero.Processeur()) // en premier : avant tout exportateur, App Insights compris
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
            // le TokenCredential vient du conteneur de services (les tests le remplacent), lu au premier export
            o.HttpClientFactory = () => new HttpClient(new JetonOtlpHandler(
                () => fournisseur!.GetRequiredService<TokenCredential>(),
                string.IsNullOrEmpty(audienceTelemetrie) ? null : $"{audienceTelemetrie}/.default")
            { InnerHandler = new HttpClientHandler() });
        }));

// Export Azure Monitor (App Insights) en plus de l'OTLP, seulement si la chaîne de connexion est posée
if (!string.IsNullOrEmpty(builder.Configuration["APPLICATIONINSIGHTS_CONNECTION_STRING"]))
{
    // 100 % des traces : l'échantillonneur par défaut (5/s) écarterait aussi des spans de l'export vers le référentiel SQL (D-V2)
    builder.Services.AddOpenTelemetry().UseAzureMonitor(o => { o.SamplingRatio = 1; o.TracesPerSecond = null; });
    // UseAzureMonitor exporte aussi les journaux : « Request starting … /api/contrats/AIF-… » (Information) porte le numéro
    foreach (var categorie in new[] { "Microsoft", "System", "Yarp" })
    {
        builder.Logging.AddFilter<OpenTelemetry.Logs.OpenTelemetryLoggerProvider>(categorie, LogLevel.Warning);
    }
}

var app = builder.Build();
fournisseur = app.Services;

if (envoyDevant)
{
    app.UseForwardedHeaders();
}

// Espace gestionnaire (#103) : page statique publique sous /app/ (Swagger garde la racine) ; ses appels
// portent le jeton du gestionnaire. CSP stricte : aucun script tiers, MSAL est servi par la gateway.
const string CspEspace = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    + "connect-src 'self' https://login.microsoftonline.com; frame-src https://login.microsoftonline.com; "
    + "base-uri 'none'; form-action 'self'; frame-ancestors 'none'";
var fichiersEspace = new PhysicalFileProvider(Path.Combine(app.Environment.WebRootPath, "app"));
app.UseDefaultFiles(new DefaultFilesOptions { RequestPath = "/app", FileProvider = fichiersEspace });
app.UseStaticFiles(new StaticFileOptions
{
    RequestPath = "/app",
    FileProvider = fichiersEspace,
    OnPrepareResponse = f => f.Context.Response.Headers.ContentSecurityPolicy = CspEspace,
});

// Page Swagger unique, à la racine : les 4 documents OpenAPI de la solution (S3-24).
// Connexion Entra en PKCE avec un seul client public (l'application agentinsurflow-rag).
// Placée avant l'authentification : la page est publique, les appels qu'elle fait portent le jeton.
app.UseSwaggerUI(ui =>
{
    ui.RoutePrefix = "";
    ui.DocumentTitle = "AgentInsurFlow — API";
    ui.SwaggerEndpoint("/rag/openapi.json", "rag");
    ui.SwaggerEndpoint("/underwriting/openapi/v1.json", "underwriting-admin");
    ui.SwaggerEndpoint("/cluster/openapi.json", "cluster");
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

// Configuration publique de l'espace : client public (PKCE), portées des services et UPN de connexion (loginHint).
// Aucun secret : tout ici est visible dans le navigateur de toute façon.
app.MapGet("/app/config.json", (IConfiguration cfg) => Results.Json(new
{
    client_id = cfg["Espace:ClientId"] ?? cfg["SWAGGER_CLIENT_ID"] ?? "",
    authority = cfg["Espace:Authority"] ?? "",
    scopes = new Dictionary<string, string>
    {
        ["rag"] = cfg["Espace:Scopes:Rag"] ?? "",
        ["underwriting"] = cfg["Espace:Scopes:Underwriting"] ?? "",
        ["cluster"] = cfg["Espace:Scopes:Cluster"] ?? "",
    },
    comptes = new Dictionary<string, string> { ["A"] = cfg["Espace:Comptes:A"] ?? "", ["B"] = cfg["Espace:Comptes:B"] ?? "" },
}))
    .ExcludeFromDescription()
    .AllowAnonymous()
    .DisableRateLimiting();

app.MapReverseProxy();

await app.RunAsync();

static IResult Probleme(int statut, string titre, string code) =>
    Results.Problem(statusCode: statut, title: titre, extensions: new Dictionary<string, object?> { ["code"] = code });

// Utilisateur et application cliente : les agents du cluster appellent en OBO pour le même gestionnaire (même oid),
// chacun avec son azp ; sans azp dans la clé, une évaluation épuiserait la fenêtre du gestionnaire.
static string Partition(HttpContext ctx) =>
    ctx.User.FindFirst("oid")?.Value is { } oid
        ? AzpOuAppid(ctx) is { } app ? $"oid:{oid}|azp:{app}" : $"oid:{oid}"
        : $"ip:{ctx.Connection.RemoteIpAddress}";

// Appelant de l'API LLM : l'application cliente (azp, ou appid d'un jeton v1), sinon repli sur l'utilisateur/IP.
static string PartitionAppelant(HttpContext ctx) =>
    AzpOuAppid(ctx) is { } app ? $"azp:{app}" : Partition(ctx);

static string? AzpOuAppid(HttpContext ctx) =>
    (ctx.User.FindFirst("azp") ?? ctx.User.FindFirst("appid"))?.Value;

// Tokens consommés (conventions GenAI d'OTel) posés sur le span de la requête. JSON : usage lu dans une copie
// tamponnée (HttpContent relu tel quel ensuite) ; flux SSE : jamais lu, donc jamais tamponné.
// Réponse encodée (gzip…) : non lue ; la gateway ne demande pas de compression à l'amont (Accept-Encoding retiré).
static bool Est(string? type, string attendu) => string.Equals(type, attendu, StringComparison.OrdinalIgnoreCase);

static async Task MesurerTokens(HttpContext ctx, HttpResponseMessage? reponse)
{
    var span = ctx.Features.Get<IHttpActivityFeature>()?.Activity;
    var type = reponse?.Content.Headers.ContentType?.MediaType;
    if (span is null || reponse is null || !(Est(type, "application/json") || Est(type, "text/event-stream")))
    {
        return;
    }
    if ((AzpOuAppid(ctx) ?? ctx.User.FindFirst("oid")?.Value) is { } appelant)
    {
        span.SetTag("appelant.azp", appelant);
    }
    // Plafond : on ne tamponne que les corps de taille annoncée ; gros ou découpé = non lu (comme le flux).
    const long plafond = 4 * 1024 * 1024;
    if (Est(type, "text/event-stream") || reponse.Content.Headers.ContentEncoding.Count > 0 || reponse.Content.Headers.ContentLength is not { } taille || taille > plafond)
    {
        span.SetTag("gen_ai.usage.mesure", "non_disponible");
        return;
    }
    try
    {
        var octets = await reponse.Content.ReadAsByteArrayAsync(ctx.RequestAborted);
        using var json = JsonDocument.Parse(octets);
        var racine = json.RootElement;
        if (racine.ValueKind != JsonValueKind.Object || !racine.TryGetProperty("usage", out var usage)
            || usage.ValueKind != JsonValueKind.Object)
        {
            return;
        }
        if (usage.TryGetProperty("prompt_tokens", out var entree) && entree.TryGetInt64(out var nbEntree))
        {
            span.SetTag("gen_ai.usage.input_tokens", nbEntree);
        }
        if (usage.TryGetProperty("completion_tokens", out var sortie) && sortie.TryGetInt64(out var nbSortie))
        {
            span.SetTag("gen_ai.usage.output_tokens", nbSortie);
        }
        if (racine.TryGetProperty("model", out var modele) && modele.ValueKind == JsonValueKind.String)
        {
            span.SetTag("gen_ai.response.model", modele.GetString());
        }
    }
    catch (JsonException)
    {
        // JSON invalide : rien à mesurer, le client reçoit quand même la réponse d'amont
    }
}

static FixedWindowRateLimiterOptions FenetreFixe(int limite, TimeSpan fenetre) =>
    new() { PermitLimit = limite, Window = fenetre, QueueLimit = 0 };

/// <summary>Santé de la gateway seule ; celle des services passe par <c>/health/rag</c> et <c>/health/underwriting</c>.</summary>
internal sealed record Sante(string Statut, string Version, string Release);

/// <summary>Point d'entrée, visible des tests (<c>WebApplicationFactory&lt;Program&gt;</c>).</summary>
public partial class Program;
