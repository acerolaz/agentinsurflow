// Gateway AgentInsurFlow : seule entrée publique de la solution (S3-18).
// Routage pur, déclaré dans appsettings.Routes.json ; aucune logique d'autorisation :
// chaque service valide lui-même les jetons qu'on lui transmet tels quels.
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

app.MapGet("/health", (IConfiguration cfg) =>
        new Sante("ok", cfg["APP_VERSION"] ?? "dev", cfg["APP_RELEASE"] ?? "dev"))
    .WithName("SanteGateway")
    .WithSummary("Santé de la gateway (versions servies)");
app.MapOpenApi(); // /openapi/v1.json

// Page Swagger unique, à la racine : les 3 documents OpenAPI de la solution (S3-24).
// Connexion Entra en PKCE avec un seul client public (l'application agentinsurflow-rag).
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

app.MapReverseProxy();

await app.RunAsync();

/// <summary>Santé de la gateway seule ; celle des services passe par <c>/health/rag</c> et <c>/health/underwriting</c>.</summary>
internal sealed record Sante(string Statut, string Version, string Release);

/// <summary>Point d'entrée, visible des tests (<c>WebApplicationFactory&lt;Program&gt;</c>).</summary>
public partial class Program;
