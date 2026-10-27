using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using OpenTelemetry.Trace;

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>TI : <c>POST …/relances</c> (#130), relance enregistrée et tracée sans envoi, jetons réels, port en mémoire.</summary>
public sealed class RelancesTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";
    private const string GestionnaireB = "oid-gestionnaire-b";

    private sealed class DepotEnMemoire : IDepotRelances
    {
        public List<(string Numero, string Texte, IReadOnlyList<string> Pieces)> Relances { get; } = [];
        public bool Decide { get; set; }
        public bool RangPris { get; set; } // un envoi simultané a pris le rang

        public Task<SituationRelance?> Situation(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(gestionnaireId == GestionnaireA && numeroContrat == "AIF-A1"
                ? new SituationRelance(Relances.Count(r => r.Numero == numeroContrat), Decide, ["releve_information", "permis"])
                : null);

        public Task<int?> Ajouter(string gestionnaireId, string numeroContrat, string texte, IReadOnlyList<string> pieces, CancellationToken ct)
        {
            if (RangPris) return Task.FromResult<int?>(null);
            Relances.Add((numeroContrat, texte, pieces));
            return Task.FromResult<int?>(Relances.Count(r => r.Numero == numeroContrat));
        }
    }

    private readonly DepotEnMemoire _depot = new();
    private readonly List<Activity> _activites = []; // alimentée par l'exportateur sur un autre thread : lire par ToArray()
    private readonly WebApplicationFactory<Program> _usine;

    public RelancesTests() => _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotRelances>();
        s.AddSingleton<IDepotRelances>(_depot);
        s.ConfigureOpenTelemetryTracerProvider(t => t.AddInMemoryExporter(_activites));
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement Corps)> Poster(string numero, string oid, string texte, params string[] pieces)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Post, $"/api/contrats/{numero}/relances")
        {
            Content = new StringContent(JsonSerializer.Serialize(new { texte, pieces }), Encoding.UTF8, "application/json"),
        };
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, "Gestionnaire"));
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var corps = JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken)).RootElement.Clone();
        return (reponse.StatusCode, corps);
    }

    [Fact]
    public async Task Trois_relances_puis_409()
    {
        var rangs = new List<int>();
        for (var i = 0; i < 3; i++)
        {
            var (statut, corps) = await Poster("AIF-A1", GestionnaireA, "Bonjour", "releve_information");
            Assert.Equal(HttpStatusCode.Created, statut);
            Assert.Equal(3, corps.GetProperty("max").GetInt32());
            rangs.Add(corps.GetProperty("rang").GetInt32());
        }
        var (quatrieme, refus) = await Poster("AIF-A1", GestionnaireA, "Bonjour", "releve_information");

        Assert.Equal([1, 2, 3], rangs);
        Assert.Equal(HttpStatusCode.Conflict, quatrieme);
        Assert.Equal("RELANCES_EPUISEES", refus.GetProperty("code").GetString());
        Assert.Equal(3, _depot.Relances.Count);
    }

    [Fact]
    public async Task Relance_autre_gestionnaire_404()
    {
        var (statut, corps) = await Poster("AIF-A1", GestionnaireB, "Bonjour", "permis");

        Assert.Equal(HttpStatusCode.NotFound, statut);
        Assert.Equal("CONTRAT_INTROUVABLE", corps.GetProperty("code").GetString());
        Assert.Empty(_depot.Relances);
    }

    [Fact]
    public async Task Texte_vide_400()
    {
        var (statut, corps) = await Poster("AIF-A1", GestionnaireA, "   ", "permis");

        Assert.Equal(HttpStatusCode.BadRequest, statut);
        Assert.Equal("TEXTE_INVALIDE", corps.GetProperty("code").GetString());
        Assert.Empty(_depot.Relances);
    }

    [Fact]
    public async Task Dossier_decide_409()
    {
        _depot.Decide = true;
        var (statut, corps) = await Poster("AIF-A1", GestionnaireA, "Bonjour", "permis");

        Assert.Equal(HttpStatusCode.Conflict, statut);
        Assert.Equal("DOSSIER_DECIDE", corps.GetProperty("code").GetString());
        Assert.Empty(_depot.Relances);
    }

    [Fact]
    public async Task Envoi_simultane_409_et_non_500()
    {
        _depot.RangPris = true;
        var (statut, corps) = await Poster("AIF-A1", GestionnaireA, "Bonjour", "permis");

        Assert.Equal(HttpStatusCode.Conflict, statut);
        Assert.Equal("RELANCE_CONCURRENTE", corps.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Texte_html_stocke_tel_quel()
    {
        await Poster("AIF-A1", GestionnaireA, "<b>x</b>", "permis");

        Assert.Equal("<b>x</b>", Assert.Single(_depot.Relances).Texte);
    }

    [Fact]
    public async Task Span_porte_le_rang_et_les_pieces_jamais_le_texte()
    {
        await Poster("AIF-A1", GestionnaireA, "Texte confidentiel de la relance", "releve_information", "permis");
        _usine.Services.GetRequiredService<TracerProvider>().ForceFlush();

        var span = Assert.Single(_activites.ToArray(), a => a.GetTagItem("relance.rang") is not null);
        Assert.Equal(1, span.GetTagItem("relance.rang"));
        Assert.Equal(3, span.GetTagItem("relance.max"));
        Assert.Equal("releve_information,permis", span.GetTagItem("relance.pieces"));
        Assert.DoesNotContain(span.TagObjects, t => t.Value?.ToString()?.Contains("confidentiel", StringComparison.Ordinal) == true);
    }

    [Fact]
    public async Task Refus_trace_avec_son_code_jamais_le_texte()
    {
        _depot.Decide = true;
        await Poster("AIF-A1", GestionnaireA, "Texte confidentiel de la relance", "permis");
        _usine.Services.GetRequiredService<TracerProvider>().ForceFlush();

        var span = Assert.Single(_activites.ToArray(), a => a.GetTagItem("relance.refus") is not null);
        Assert.Equal("DOSSIER_DECIDE", span.GetTagItem("relance.refus"));
        Assert.Null(span.GetTagItem("relance.rang"));
        Assert.DoesNotContain(span.TagObjects, t => t.Value?.ToString()?.Contains("confidentiel", StringComparison.Ordinal) == true);
    }
}
