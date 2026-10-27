using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>TI : <c>GET …/etat</c> (progression de l'espace gestionnaire), jetons réels, port <see cref="IDepotEtat"/> en mémoire.</summary>
public sealed class LectureEtatTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";
    private const string GestionnaireB = "oid-gestionnaire-b";
    private static readonly DateTimeOffset Debut = new(2026, 10, 27, 10, 0, 0, TimeSpan.Zero);

    private sealed class DepotEnMemoire : IDepotEtat
    {
        public Task<EtatLu?> LireEtat(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(gestionnaireId != GestionnaireA ? null : numeroContrat switch
            {
                "AIF-A1" => new EtatLu("EN_COURS", 2, 1,
                    [new RapportLu("pieces", "llm", null, "t-1", Debut), new RapportLu("analyste", "repli", "llm_ko", "t-1", Debut.AddSeconds(3.1))],
                    new Dictionary<string, string>
                    {
                        ["dossier"] = """{"code_postal":"75011"}""",
                        ["pieces"] = """{"statut":"incomplet","manquantes":["releve_information"],"note":""}""",
                        ["pilotage"] = """{"tour":2}""",
                    }),
                "AIF-A2" => new EtatLu(null, 0, 0, [], new Dictionary<string, string>()),
                _ => null,
            });
    }

    private readonly WebApplicationFactory<Program> _usine;

    public LectureEtatTests() => _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotEtat>();
        s.AddSingleton<IDepotEtat, DepotEnMemoire>();
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement Corps)> Get(string numero, string oid)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, $"/api/contrats/{numero}/etat");
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, "Gestionnaire"));
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var corps = JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken)).RootElement.Clone();
        return (reponse.StatusCode, corps);
    }

    [Fact]
    public async Task Lire_etat_rend_rapports_et_sections_lisibles_seulement()
    {
        var (statut, corps) = await Get("AIF-A1", GestionnaireA);

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal("EN_COURS", corps.GetProperty("statut_parcours").GetString());
        Assert.Equal(2, corps.GetProperty("tentative").GetInt32());
        Assert.Equal(1, corps.GetProperty("nb_relances").GetInt32());
        Assert.Equal(["pieces"], corps.GetProperty("sections").EnumerateObject().Select(p => p.Name));
        Assert.Equal("releve_information", corps.GetProperty("sections").GetProperty("pieces").GetProperty("manquantes")[0].GetString());
        var rapports = corps.GetProperty("rapports").EnumerateArray().ToList();
        Assert.Equal(["pieces", "analyste"], rapports.Select(r => r.GetProperty("agent").GetString()));
        Assert.Equal("llm_ko", rapports[1].GetProperty("cause").GetString());
        Assert.Equal("t-1", rapports[0].GetProperty("trace_id").GetString());
        Assert.Equal(Debut.AddSeconds(3.1), rapports[1].GetProperty("cree_le").GetDateTimeOffset());
        Assert.DoesNotContain("75011", corps.GetRawText(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Lire_etat_sans_evaluation_200_vide()
    {
        var (statut, corps) = await Get("AIF-A2", GestionnaireA);

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal(JsonValueKind.Null, corps.GetProperty("statut_parcours").ValueKind);
        Assert.Empty(corps.GetProperty("rapports").EnumerateArray());
    }

    [Fact]
    public async Task Lire_etat_autre_gestionnaire_404()
    {
        var (statut, corps) = await Get("AIF-A1", GestionnaireB);

        Assert.Equal(HttpStatusCode.NotFound, statut);
        Assert.Equal("CONTRAT_INTROUVABLE", corps.GetProperty("code").GetString());
    }
}
