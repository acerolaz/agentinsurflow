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

/// <summary>TI : <c>GET …/souscripteur</c>, fiche du lead dans le détail du dossier (exception du 27/10), port en mémoire.</summary>
public sealed class FicheSouscripteurTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";
    private const string GestionnaireB = "oid-gestionnaire-b";

    private static readonly FicheSouscripteur Fiche = new("Mme", "Durand", "Alice", "3 rue des Lilas", "69003",
        "0612345678", "alice@exemple.invalid", new VehiculeContrat("Peugeot", "208", "AB-123-CD", 5, "prive",
        "1.2 PureTech", "VF3TEST", new DateOnly(2019, 3, 15), "garage", "69003"));

    private sealed class DepotEnMemoire : IDepotFicheSouscripteur
    {
        public Task<FicheSouscripteur?> LireFiche(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(gestionnaireId == GestionnaireA && numeroContrat == "AIF-A1" ? Fiche : null);
    }

    private readonly WebApplicationFactory<Program> _usine;

    public FicheSouscripteurTests() => _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotFicheSouscripteur>();
        s.AddSingleton<IDepotFicheSouscripteur, DepotEnMemoire>();
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement Corps)> Get(string numero, string oid)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, $"/api/contrats/{numero}/souscripteur");
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, "Gestionnaire"));
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var brut = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        return (reponse.StatusCode, JsonDocument.Parse(brut).RootElement.Clone());
    }

    [Fact]
    public async Task Fiche_du_gestionnaire_200_avec_coordonnees_et_vehicule()
    {
        var (statut, corps) = await Get("AIF-A1", GestionnaireA);

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal(("Mme", "Durand", "Alice", "3 rue des Lilas", "69003", "0612345678", "alice@exemple.invalid"),
            (corps.GetProperty("civilite").GetString(), corps.GetProperty("nom").GetString(), corps.GetProperty("prenom").GetString(),
             corps.GetProperty("adresse").GetString(), corps.GetProperty("code_postal").GetString(),
             corps.GetProperty("mobile").GetString(), corps.GetProperty("email").GetString()));
        Assert.Equal("AB-123-CD", corps.GetProperty("vehicule").GetProperty("immatriculation").GetString());
    }

    [Fact]
    public async Task Fiche_d_un_autre_gestionnaire_404_comme_un_inexistant()
    {
        var (autre, corps) = await Get("AIF-A1", GestionnaireB);
        var (inexistant, _) = await Get("AIF-ZZ", GestionnaireA);

        Assert.Equal((HttpStatusCode.NotFound, HttpStatusCode.NotFound), (autre, inexistant));
        Assert.Equal("CONTRAT_INTROUVABLE", corps.GetProperty("code").GetString());
    }
}
