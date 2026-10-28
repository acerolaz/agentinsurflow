using System.Diagnostics;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Logs;
using OpenTelemetry.Trace;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>Spans et journaux : numéro de contrat masqué (#65), un seul span serveur par requête avec App Insights (#54).</summary>
public sealed class TelemetrieTests(Backends backends) : IClassFixture<Backends>
{
    private const string AppInsights = "InstrumentationKey=00000000-0000-0000-0000-000000000000";

    /// <summary>Collecte les spans terminés, donc après les enrichissements.</summary>
    private sealed class Collecteur(List<Activity> activites) : BaseProcessor<Activity>
    {
        public override void OnEnd(Activity data)
        {
            lock (activites)
            {
                activites.Add(data);
            }
        }
    }

    /// <summary>Collecte le texte de chaque enregistrement de journal exporté (message, corps, attributs).</summary>
    private sealed class CollecteurJournaux(List<string> textes) : BaseProcessor<LogRecord>
    {
        public override void OnEnd(LogRecord data)
        {
            var attributs = data.Attributes?.Select(a => $"{a.Key}={a.Value}") ?? [];
            lock (textes)
            {
                textes.Add(string.Join(' ', [data.FormattedMessage, data.Body, .. attributs]));
            }
        }
    }

    private static Activity[] SpansDe(List<Activity> activites, string trace)
    {
        lock (activites)
        {
            return [.. activites.Where(a => a.TraceId.ToString() == trace)];
        }
    }

    private async Task<(Activity[] Spans, string[] Journaux)> Executer(string? chaineAppInsights, string chemin)
    {
        var activites = new List<Activity>();
        var journaux = new List<string>();
        using var usine = backends.Gateway(chaineAppInsights is null
            ? []
            : [("APPLICATIONINSIGHTS_CONNECTION_STRING", chaineAppInsights)])
            .WithWebHostBuilder(b => b.ConfigureServices(s =>
            {
                s.ConfigureOpenTelemetryTracerProvider(t => t.AddProcessor(new Collecteur(activites)));
                s.AddOpenTelemetry().WithLogging(l => l.AddProcessor(new CollecteurJournaux(journaux)));
            }));
        // un avertissement d'une catégorie filtrée à Warning qui porte le numéro (ex. « Request failed » de YARP)
        usine.Services.GetRequiredService<ILoggerFactory>().CreateLogger("Yarp.ReverseProxy").Log(
            LogLevel.Warning, default, "Échec du renvoi vers /api/contrats/AIF-2026-000001", null, (message, _) => message);
        using var client = usine.CreateClient();
        // trace propre à la requête : les fournisseurs reçoivent aussi les spans des tests parallèles
        var trace = ActivityTraceId.CreateRandom().ToString();
        using var requete = Requete("GET", chemin, Creer(Audience("underwriting"), TousLesRoles));
        requete.Headers.Add("traceparent", $"00-{trace}-0123456789abcdef-01");
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        // le premier démarrage d'Azure Monitor du processus est lent : attendre le span (sauf /health, qui n'en produit pas)
        for (var i = 0; i < 60 && chemin != "/health" && !SpansDe(activites, trace).Any(a => a.Kind == ActivityKind.Client); i++)
        {
            await Task.Delay(50, TestContext.Current.CancellationToken);
        }
        lock (activites)
        lock (journaux)
        {
            return ([.. SpansDe(activites, trace)], [.. journaux]);
        }
    }

    [Theory]
    [InlineData(null)]
    [InlineData(AppInsights)]
    public async Task Spans_sans_numero_de_contrat(string? chaineAppInsights)
    {
        var (spans, _) = await Executer(chaineAppInsights, "/api/contrats/AIF-2026-000001");

        Assert.Contains(spans, a => a.Kind == ActivityKind.Server);
        Assert.Contains(spans, a => a.Kind == ActivityKind.Client); // le renvoi YARP vers le backend
        Assert.All(spans, a =>
        {
            Assert.DoesNotContain("AIF-", a.DisplayName);
            Assert.All(a.TagObjects, t => Assert.DoesNotContain("AIF-", t.Value?.ToString() ?? ""));
        });
    }

    [Fact]
    public async Task Avec_chaine_app_insights_un_seul_span_serveur_par_requete()
    {
        var (spans, _) = await Executer(AppInsights, "/api/contrats/AIF-2026-000001");

        // le backend WireMock tourne dans ce processus et trace aussi sa réception : seul le span fils du traceparent est la gateway
        Assert.Single(spans, a => a.Kind == ActivityKind.Server && a.ParentSpanId.ToString() == "0123456789abcdef");
    }

    [Fact]
    public async Task Avec_chaine_app_insights_le_filtre_health_tient()
    {
        var (spans, _) = await Executer(AppInsights, "/health");

        Assert.DoesNotContain(spans, a => a.Kind == ActivityKind.Server);
    }

    [Fact]
    public async Task Avec_chaine_app_insights_journaux_sans_numero_de_contrat()
    {
        var (_, journaux) = await Executer(AppInsights, "/api/contrats/AIF-2026-000001");

        Assert.Contains(journaux, j => j.Contains("{numero_contrat}", StringComparison.Ordinal));
        Assert.All(journaux, j => Assert.DoesNotContain("AIF-", j));
    }
}
