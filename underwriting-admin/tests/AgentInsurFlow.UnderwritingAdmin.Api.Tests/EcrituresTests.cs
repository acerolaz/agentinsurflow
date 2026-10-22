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

/// <summary>TI : routes d'écriture <c>/api/contrats/{numero}/brouillon|statut</c>, jetons réels, port <see cref="IDepotEcritures"/> en mémoire.</summary>
public sealed class EcrituresTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";

    private sealed class DepotEnMemoire : IDepotEcritures
    {
        public static readonly List<string> Appels = [];

        public Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
            PrimeBrouillon? prime, CancellationToken ct)
        {
            Appels.Add($"brouillon {gestionnaireId} {numeroContrat} {fiche.Decision} {fiche.RegleIds[0]} {prime?.PrimeTtc}");
            return Task.FromResult(gestionnaireId == GestionnaireA && numeroContrat == "AIF-A1");
        }

        public Task<ResultatEcriture> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
            CancellationToken ct)
        {
            Appels.Add($"statut {gestionnaireId} {numeroContrat} {changement.StatutCible} {changement.Validation}");
            if (numeroContrat == "AIF-SANS-BROUILLON") return Task.FromResult(new ResultatEcriture(false, "DECISION_ABSENTE"));
            return Task.FromResult(new ResultatEcriture(gestionnaireId == GestionnaireA && numeroContrat == "AIF-A1", null));
        }
    }

    private readonly WebApplicationFactory<Program> _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotEcritures>();
        s.AddSingleton<IDepotEcritures, DepotEnMemoire>();
    }));

    public EcrituresTests() => DepotEnMemoire.Appels.Clear();

    public void Dispose() => _usine.Dispose();

    private const string Brouillon =
        """{"fiche":{"decision":"ACCEPTE","contrat_type":"tous_risques","score":0.8,"version_bareme":"v1","regle_ids":["R1"],"motifs":["m"],"citations":["c"]},"prime":{"prime_ttc":512.4,"periodicite":"mensuelle","date_effet":"2026-11-01"}}""";

    private async Task<(HttpStatusCode Statut, JsonElement? Corps)> Put(string chemin, string json, string? oid, params string[] roles)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Put, chemin) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
        if (oid is not null)
        {
            requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, roles));
        }
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var texte = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        return (reponse.StatusCode, texte.Length == 0 ? null : JsonDocument.Parse(texte).RootElement.Clone());
    }

    [Fact]
    public async Task Brouillon_nominal_204_et_corps_snake_case_lu_par_le_port()
    {
        var (statut, corps) = await Put("/api/contrats/AIF-A1/brouillon", Brouillon, GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.NoContent, statut);
        Assert.Null(corps);
        Assert.Equal(["brouillon oid-gestionnaire-a AIF-A1 ACCEPTE R1 512.4"], DepotEnMemoire.Appels);
    }

    [Fact]
    public async Task Brouillon_sans_prime_204()
    {
        var (statut, _) = await Put("/api/contrats/AIF-A1/brouillon",
            """{"fiche":{"decision":"REFUSE","contrat_type":"t","score":1,"version_bareme":"v","regle_ids":["R9"],"motifs":[],"citations":[]},"prime":null}""",
            GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.NoContent, statut);
    }

    [Fact]
    public async Task Brouillon_decision_inconnue_400_avec_le_code()
    {
        var (statut, corps) = await Put("/api/contrats/AIF-A1/brouillon", Brouillon.Replace("ACCEPTE", "PEUTETRE", StringComparison.Ordinal),
            GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.BadRequest, statut);
        Assert.Equal("DECISION_INCONNUE", corps!.Value.GetProperty("code").GetString());
        Assert.Empty(DepotEnMemoire.Appels);
    }

    [Fact]
    public async Task Brouillon_absent_et_autre_gestionnaire_meme_404()
    {
        var (statutAbsent, absent) = await Put("/api/contrats/AIF-ZZZ/brouillon", Brouillon, GestionnaireA, "Gestionnaire");
        var (statutAutre, autre) = await Put("/api/contrats/AIF-A1/brouillon", Brouillon, "oid-gestionnaire-b", "Gestionnaire");

        Assert.Equal(HttpStatusCode.NotFound, statutAbsent);
        Assert.Equal(statutAbsent, statutAutre);
        Assert.Equal("CONTRAT_INTROUVABLE", absent!.Value.GetProperty("code").GetString());
        Assert.Equal(Sans(absent.Value), Sans(autre!.Value));
    }

    private static string Sans(JsonElement p) =>
        string.Join('|', p.EnumerateObject().Where(x => x.Name != "traceId").Select(x => $"{x.Name}={x.Value}"));

    [Fact]
    public async Task Statut_nominal_204_et_le_port_recoit_le_gestionnaire_du_jeton()
    {
        var (statut, _) = await Put("/api/contrats/AIF-A1/statut", """{"statut":"REFUSE","validation":"CORRIGEE"}""", GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.NoContent, statut);
        Assert.Equal(["statut oid-gestionnaire-a AIF-A1 REFUSE CORRIGEE"], DepotEnMemoire.Appels);
    }

    [Fact]
    public async Task Statut_final_sans_validation_400_VALIDATION_EXIGEE()
    {
        var (statut, corps) = await Put("/api/contrats/AIF-A1/statut", """{"statut":"ACCEPTE","validation":null}""", GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.BadRequest, statut);
        Assert.Equal("VALIDATION_EXIGEE", corps!.Value.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Statut_validation_sans_brouillon_400_DECISION_ABSENTE()
    {
        var (statut, corps) = await Put("/api/contrats/AIF-SANS-BROUILLON/statut", """{"statut":"ACCEPTE","validation":"VALIDEE"}""", GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.BadRequest, statut);
        Assert.Equal("DECISION_ABSENTE", corps!.Value.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Statut_absent_404()
    {
        var (statut, corps) = await Put("/api/contrats/AIF-ZZZ/statut", """{"statut":"EN_ANALYSE"}""", GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.NotFound, statut);
        Assert.Equal("CONTRAT_INTROUVABLE", corps!.Value.GetProperty("code").GetString());
    }

    [Theory]
    [InlineData("brouillon")]
    [InlineData("statut")]
    public async Task Sans_jeton_401(string route) =>
        Assert.Equal(HttpStatusCode.Unauthorized, (await Put($"/api/contrats/AIF-A1/{route}", "{}", null)).Statut);

    [Theory]
    [InlineData("brouillon")]
    [InlineData("statut")]
    public async Task Sans_role_Gestionnaire_403(string route) =>
        Assert.Equal(HttpStatusCode.Forbidden, (await Put($"/api/contrats/AIF-A1/{route}", "{}", GestionnaireA, "Telemetrie")).Statut);
}
