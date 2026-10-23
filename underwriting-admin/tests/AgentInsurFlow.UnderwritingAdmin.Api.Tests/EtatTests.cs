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

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>TI : <c>PUT …/etat</c> (mémoire long terme du dossier, D100), jetons réels, dépôt en mémoire qui rejoue le contrat d'idempotence du port.</summary>
public sealed class EtatTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";
    private const string GestionnaireB = "oid-gestionnaire-b";

    private sealed class DepotEnMemoire : IDepotEcritures
    {
        private readonly Dictionary<string, string> _proprietaires = new() { ["AIF-A1"] = GestionnaireA };

        public Dictionary<string, (string Statut, int Tentative)> Etats { get; } = new();
        public Dictionary<(string Numero, string Section, int Tentative), string> Sections { get; } = new();
        public HashSet<(string Numero, string Agent, int Tentative, string Trace)> Rapports { get; } = new();
        public HashSet<(string Numero, int Tentative, int Tour)> Tours { get; } = new();

        public Task<string?> StatutContrat(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(_proprietaires.TryGetValue(numeroContrat, out var g) && g == gestionnaireId ? "EN_ANALYSE" : null);

        public Task<bool> EnregistrerEtat(string gestionnaireId, string numeroContrat, EtatEntrant etat, CancellationToken ct)
        {
            if (!_proprietaires.TryGetValue(numeroContrat, out var g) || g != gestionnaireId) return Task.FromResult(false);
            Etats[numeroContrat] = (etat.StatutParcours, etat.Tentative);
            foreach (var s in etat.Sections) Sections[(numeroContrat, s.Section, etat.Tentative)] = s.Contenu;
            foreach (var r in etat.Rapports) Rapports.Add((numeroContrat, r.Agent, etat.Tentative, r.TraceId));
            foreach (var t in etat.Tours) Tours.Add((numeroContrat, etat.Tentative, t.Tour));
            return Task.FromResult(true);
        }

        public Task<bool> EnregistrerObservations(string gestionnaireId, string numeroContrat, string observations, CancellationToken ct) =>
            throw new NotSupportedException();

        public Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
            PrimeBrouillon? prime, CancellationToken ct) => throw new NotSupportedException();

        public Task<ResultatEcriture> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
            CancellationToken ct) => throw new NotSupportedException();
    }

    private readonly DepotEnMemoire _depot = new();

    private readonly WebApplicationFactory<Program> _usine;

    public EtatTests() => _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotEcritures>();
        s.AddSingleton<IDepotEcritures>(_depot);
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement? Corps)> Put(string numero, string oid, string json)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Put, $"/api/contrats/{numero}/etat")
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, "Gestionnaire"));
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var texte = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        return (reponse.StatusCode, texte.Length == 0 ? null : JsonDocument.Parse(texte).RootElement.Clone());
    }

    private static string Corps(string section = "risque") => JsonSerializer.Serialize(new
    {
        statut_parcours = "EN_COURS",
        tentative = 1,
        sections = new[] { new { section, contenu = new { score = 0.4 } } },
        rapports = new[] { new { agent = "risque", rapport = new { resume = "ok" }, mode = "llm", cause = (string?)null, version_prompt = "v1", trace_id = "t-1" } },
        tours = new[] { new { tour = 1, outil_appele = "evaluer_risque", precondition = "pieces_ok", mode = "llm" } },
    });

    [Fact]
    public async Task Deux_put_identiques_une_ligne_d_etat_et_un_seul_rapport()
    {
        var (premier, _) = await Put("AIF-A1", GestionnaireA, Corps());
        var (second, _) = await Put("AIF-A1", GestionnaireA, Corps());

        Assert.Equal(HttpStatusCode.NoContent, premier);
        Assert.Equal(HttpStatusCode.NoContent, second);
        var etat = Assert.Single(_depot.Etats);
        Assert.Equal(("EN_COURS", 1), etat.Value);
        Assert.Single(_depot.Sections);
        Assert.Single(_depot.Rapports);
        Assert.Single(_depot.Tours);
    }

    [Fact]
    public async Task Autre_gestionnaire_404_et_aucune_ligne()
    {
        var (statut, corps) = await Put("AIF-A1", GestionnaireB, Corps());

        Assert.Equal(HttpStatusCode.NotFound, statut);
        Assert.Equal("CONTRAT_INTROUVABLE", corps!.Value.GetProperty("code").GetString());
        Assert.Empty(_depot.Etats);
        Assert.Empty(_depot.Sections);
        Assert.Empty(_depot.Rapports);
        Assert.Empty(_depot.Tours);
    }

    [Fact]
    public async Task Section_inconnue_400_et_aucune_ligne()
    {
        var (statut, corps) = await Put("AIF-A1", GestionnaireA, Corps("identite"));

        Assert.Equal(HttpStatusCode.BadRequest, statut);
        Assert.Equal("SECTION_INCONNUE", corps!.Value.GetProperty("code").GetString());
        Assert.Empty(_depot.Etats);
    }
}
