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

/// <summary>TI : <c>PUT …/observations</c> puis <c>GET …</c>, jetons réels, dépôt unique en mémoire (écriture et lecture).</summary>
public sealed class ObservationsTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";
    private const string GestionnaireB = "oid-gestionnaire-b";

    private sealed class DepotEnMemoire : IDepotEcritures, IDepotDossiers
    {
        // numéro → (gestionnaire, statut, observations)
        private readonly Dictionary<string, (string Gestionnaire, string Statut, string? Observations)> _contrats = new()
        {
            ["AIF-A1"] = (GestionnaireA, "EN_ANALYSE", null),
            ["AIF-FIGE"] = (GestionnaireA, "ACCEPTE", null),
        };

        public Task<string?> StatutContrat(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(_contrats.TryGetValue(numeroContrat, out var c) && c.Gestionnaire == gestionnaireId ? c.Statut : null);

        public Task<bool> EnregistrerObservations(string gestionnaireId, string numeroContrat, string observations, CancellationToken ct)
        {
            if (!_contrats.TryGetValue(numeroContrat, out var c) || c.Gestionnaire != gestionnaireId) return Task.FromResult(false);
            _contrats[numeroContrat] = c with { Observations = observations };
            return Task.FromResult(true);
        }

        public Task<VueContrat?> Trouver(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(_contrats.TryGetValue(numeroContrat, out var c) && c.Gestionnaire == gestionnaireId
                ? new VueContrat(numeroContrat, "25-39", 4, "75", 0.9, 1, 0, 0, "tous_risques", DateTimeOffset.UnixEpoch,
                    new DateOnly(2026, 1, 1), 91, 5, "prive", 0, 0, true, c.Observations)
                : null);

        public Task<IReadOnlyList<VueContrat>> Lister(string gestionnaireId, int limit, int offset, CancellationToken ct) =>
            throw new NotSupportedException();

        public Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
            PrimeBrouillon? prime, CancellationToken ct) => throw new NotSupportedException();

        public Task<ResultatEcriture> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
            CancellationToken ct) => throw new NotSupportedException();
    }

    private readonly WebApplicationFactory<Program> _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotEcritures>();
        s.RemoveAll<IDepotDossiers>();
        s.AddSingleton<DepotEnMemoire>();
        s.AddSingleton<IDepotEcritures>(p => p.GetRequiredService<DepotEnMemoire>());
        s.AddSingleton<IDepotDossiers>(p => p.GetRequiredService<DepotEnMemoire>());
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement? Corps)> Appeler(HttpMethod methode, string numero, string oid, string? json = null)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(methode, $"/api/contrats/{numero}");
        if (json is not null)
        {
            requete.RequestUri = new Uri($"/api/contrats/{numero}/observations", UriKind.Relative);
            requete.Content = new StringContent(json, Encoding.UTF8, "application/json");
        }
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, "Gestionnaire"));
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var texte = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        return (reponse.StatusCode, texte.Length == 0 ? null : JsonDocument.Parse(texte).RootElement.Clone());
    }

    private static string Corps(string texte) => JsonSerializer.Serialize(new { observations = texte });

    private async Task<string?> Observations(string numero, string oid)
    {
        var (_, corps) = await Appeler(HttpMethod.Get, numero, oid);
        return corps!.Value.GetProperty("observations").GetString();
    }

    [Fact]
    public async Task Put_puis_get_rend_le_texte_et_la_valeur_est_ecrasee()
    {
        Assert.Null(await Observations("AIF-A1", GestionnaireA));

        var (statut, _) = await Appeler(HttpMethod.Put, "AIF-A1", GestionnaireA, Corps("premier"));
        Assert.Equal(HttpStatusCode.NoContent, statut);
        Assert.Equal("premier", await Observations("AIF-A1", GestionnaireA));

        await Appeler(HttpMethod.Put, "AIF-A1", GestionnaireA, Corps("second"));
        Assert.Equal("second", await Observations("AIF-A1", GestionnaireA));
    }

    [Fact]
    public async Task Autre_gestionnaire_404_et_valeur_inchangee()
    {
        await Appeler(HttpMethod.Put, "AIF-A1", GestionnaireA, Corps("a"));

        var (statut, corps) = await Appeler(HttpMethod.Put, "AIF-A1", GestionnaireB, Corps("pirate"));

        Assert.Equal(HttpStatusCode.NotFound, statut);
        Assert.Equal("CONTRAT_INTROUVABLE", corps!.Value.GetProperty("code").GetString());
        Assert.Equal("a", await Observations("AIF-A1", GestionnaireA));
    }

    [Fact]
    public async Task Deux_mille_et_un_caracteres_400_avec_le_code()
    {
        var (statut, corps) = await Appeler(HttpMethod.Put, "AIF-A1", GestionnaireA, Corps(new string('a', 2001)));

        Assert.Equal(HttpStatusCode.BadRequest, statut);
        Assert.Equal("OBSERVATIONS_TROP_LONGUES", corps!.Value.GetProperty("code").GetString());
        Assert.Null(await Observations("AIF-A1", GestionnaireA));
    }

    [Fact]
    public async Task Statut_fige_409_avec_le_code()
    {
        var (statut, corps) = await Appeler(HttpMethod.Put, "AIF-FIGE", GestionnaireA, Corps("x"));

        Assert.Equal(HttpStatusCode.Conflict, statut);
        Assert.Equal("STATUT_FIGE", corps!.Value.GetProperty("code").GetString());
    }
}
