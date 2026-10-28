using System.Diagnostics;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using OpenTelemetry;
using OpenTelemetry.Trace;
using static AgentInsurFlow.Gateway.Api.Tests.JetonsDeTest;

namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>Spans HTTP : numéro de contrat masqué (#65) et un seul span serveur par requête avec App Insights (#54).</summary>
public sealed class TelemetrieTests
{
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

    private static async Task<Activity[]> Requete(string? chaineAppInsights)
    {
        var activites = new List<Activity>();
        using var usine = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            if (chaineAppInsights is not null)
            {
                b.UseSetting("APPLICATIONINSIGHTS_CONNECTION_STRING", chaineAppInsights);
            }
            b.AvecEntraDeTest().ConfigureServices(s =>
                s.ConfigureOpenTelemetryTracerProvider(t => t.AddProcessor(new Collecteur(activites))));
        });
        using var client = usine.CreateClient();
        // trace propre à la requête : les fournisseurs reçoivent aussi les spans des tests parallèles
        var trace = ActivityTraceId.CreateRandom().ToString();
        using var requete = new HttpRequestMessage(HttpMethod.Get, "/api/contrats/AIF-2026-000001");
        requete.Headers.Add("traceparent", $"00-{trace}-0123456789abcdef-01");
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        await Task.Delay(200, TestContext.Current.CancellationToken);
        lock (activites)
        {
            return [.. activites.Where(a => a.TraceId.ToString() == trace)];
        }
    }

    [Fact]
    public void Masquer_remplace_le_numero() =>
        Assert.Equal("/v1/souscriptions/{numero_contrat}/evaluation",
            MasquageNumero.Masquer("/v1/souscriptions/AIF-2026-000001/evaluation"));

    [Fact]
    public async Task Span_serveur_sans_numero_de_contrat()
    {
        var activites = await Requete(null);

        Assert.Contains(activites, a => a.Kind == ActivityKind.Server);
        Assert.All(activites, a =>
        {
            Assert.DoesNotContain("AIF-", a.DisplayName);
            Assert.All(a.TagObjects, t => Assert.DoesNotContain("AIF-", t.Value?.ToString() ?? ""));
        });
    }

    [Fact]
    public async Task Avec_chaine_app_insights_un_seul_span_serveur_par_requete()
    {
        var activites = await Requete("InstrumentationKey=00000000-0000-0000-0000-000000000000");

        Assert.Single(activites, a => a.Kind == ActivityKind.Server);
    }
}
