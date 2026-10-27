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

/// <summary>TI : <c>GET …/contrat</c> (#101), contrat généré après ACCEPTE, jetons réels, port en mémoire.</summary>
public sealed class ContratGenereTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";
    private const string GestionnaireB = "oid-gestionnaire-b";

    private static readonly ContratGenere Accepte = new("AIF-A1", "tiers_plus", "standard", new DateOnly(2026, 11, 1),
        "612.40", "51.03", "bareme-2026.1", "formule-2026.1", ["Profil sans sinistre"], ["Code des assurances, art. A121-1"],
        GestionnaireA, new DateTimeOffset(2026, 10, 27, 10, 0, 0, TimeSpan.Zero),
        new SouscripteurContrat("Durand", "Alice", new DateOnly(1990, 1, 2), "3 rue des Lilas", "69003", "PERMIS42", new DateOnly(2010, 5, 6),
            "0612345678", "alice@exemple.invalid", "FR"),
        new VehiculeContrat("Peugeot", "208", "AB-123-CD", 5, "prive", "1.2 PureTech", "VF3TEST", new DateOnly(2019, 3, 15), "garage", "69003"),
        0.85, [new GarantieContrat("responsabilite_civile", 0m), new GarantieContrat("assistance_0_km", null)]);

    private sealed class DepotEnMemoire : IDepotContratGenere
    {
        public Task<(ContratGenere? Contrat, bool Existe)> LireContratGenere(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult<(ContratGenere?, bool)>(gestionnaireId != GestionnaireA ? (null, false) : numeroContrat switch
            {
                "AIF-A1" => (Accepte, true),
                "AIF-A2" => (null, true),
                _ => (null, false),
            });
    }

    private readonly WebApplicationFactory<Program> _usine;

    public ContratGenereTests() => _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotContratGenere>();
        s.AddSingleton<IDepotContratGenere, DepotEnMemoire>();
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement Corps, string Brut)> Get(string numero, string oid)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, $"/api/contrats/{numero}/contrat");
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, "Gestionnaire"));
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var brut = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        return (reponse.StatusCode, JsonDocument.Parse(brut).RootElement.Clone(), brut);
    }

    [Fact]
    public async Task Contrat_accepte_200_avec_les_parties_au_contrat_et_les_garanties()
    {
        var (statut, corps, _) = await Get("AIF-A1", GestionnaireA);

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal("AIF-A1", corps.GetProperty("numero_contrat").GetString());
        Assert.Equal("612.40", corps.GetProperty("prime_ttc_annuelle").GetString());
        Assert.Equal("51.03", corps.GetProperty("prime_mensuelle").GetString());
        Assert.Equal("formule-2026.1", corps.GetProperty("version_formule").GetString());
        Assert.Equal("2026-11-01", corps.GetProperty("date_effet").GetString());
        Assert.Equal(GestionnaireA, corps.GetProperty("valide_par").GetString());
        Assert.Equal("Code des assurances, art. A121-1", corps.GetProperty("citations")[0].GetString());
        // Exception assumée (contrat imprimé, ACCEPTE seulement) : identité, coordonnées, véhicule et garanties (modèle d'Acerola, 27/10).
        var souscripteur = corps.GetProperty("souscripteur");
        Assert.Equal(("Durand", "Alice", "3 rue des Lilas", "69003", "PERMIS42", "1990-01-02"),
            (souscripteur.GetProperty("nom").GetString(), souscripteur.GetProperty("prenom").GetString(),
             souscripteur.GetProperty("adresse").GetString(), souscripteur.GetProperty("code_postal").GetString(),
             souscripteur.GetProperty("permis_numero").GetString(), souscripteur.GetProperty("date_naissance").GetString()));
        Assert.Equal(("0612345678", "alice@exemple.invalid", "FR"),
            (souscripteur.GetProperty("telephone").GetString(), souscripteur.GetProperty("email").GetString(),
             souscripteur.GetProperty("permis_pays").GetString()));
        var vehicule = corps.GetProperty("vehicule");
        Assert.Equal(("AB-123-CD", "VF3TEST", "2019-03-15", "garage"),
            (vehicule.GetProperty("immatriculation").GetString(), vehicule.GetProperty("vin").GetString(),
             vehicule.GetProperty("date_mise_circulation").GetString(), vehicule.GetProperty("mode_stationnement").GetString()));
        Assert.Equal(0.85, corps.GetProperty("crm_bonus_malus").GetDouble());
        var garanties = corps.GetProperty("garanties");
        Assert.Equal(("responsabilite_civile", 0m), (garanties[0].GetProperty("type").GetString(), garanties[0].GetProperty("franchise").GetDecimal()));
        Assert.Equal(JsonValueKind.Null, garanties[1].GetProperty("franchise").ValueKind);
    }

    [Fact]
    public async Task Contrat_en_analyse_409()
    {
        var (statut, corps, _) = await Get("AIF-A2", GestionnaireA);

        Assert.Equal(HttpStatusCode.Conflict, statut);
        Assert.Equal("CONTRAT_NON_ACCEPTE", corps.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Contrat_autre_gestionnaire_404()
    {
        var (statut, corps, _) = await Get("AIF-A1", GestionnaireB);

        Assert.Equal(HttpStatusCode.NotFound, statut);
        Assert.Equal("CONTRAT_INTROUVABLE", corps.GetProperty("code").GetString());
    }
}
