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

/// <summary>TI : routes <c>/api/contrats</c>, jetons réels, contrôle BOLA ; le port <see cref="IDepotDossiers"/> est en mémoire.</summary>
public sealed class ContratsTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";
    private const string GestionnaireB = "oid-gestionnaire-b";

    private sealed class DepotEnMemoire : IDepotDossiers
    {
        private static readonly (string Gestionnaire, VueContrat Vue)[] Lignes =
        [
            (GestionnaireA, Vue("AIF-A1")),
            (GestionnaireA, Vue("AIF-A2")),
            (GestionnaireB, Vue("AIF-B1")),
        ];

        public Task<IReadOnlyList<VueContrat>> Lister(string gestionnaireId, int limit, int offset, CancellationToken ct) =>
            Task.FromResult<IReadOnlyList<VueContrat>>(
                Lignes.Where(l => l.Gestionnaire == gestionnaireId).Select(l => l.Vue).Skip(offset).Take(limit).ToList());

        public Task<IReadOnlyList<PieceDeclaree>?> ListerPieces(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            throw new NotSupportedException();

        public Task<VueContrat?> Trouver(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(Lignes.Where(l => l.Gestionnaire == gestionnaireId && l.Vue.NumeroContrat == numeroContrat)
                .Select(l => l.Vue).FirstOrDefault());
    }

    private static VueContrat Vue(string numero) =>
        new(numero, "25-39", 4, "75", 0.9, 1, 0, 0, "tous_risques", new DateTimeOffset(2026, 10, 1, 8, 0, 0, TimeSpan.Zero),
            new DateOnly(2026, 1, 1), 91, 5, "prive", 0, 0, true, null);

    private readonly WebApplicationFactory<Program> _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotDossiers>();
        s.AddSingleton<IDepotDossiers, DepotEnMemoire>();
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement Corps)> Get(string chemin, string oid, params string[] roles)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, chemin);
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, roles));
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var corps = JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken)).RootElement.Clone();
        return (reponse.StatusCode, corps);
    }

    [Fact]
    public async Task Portefeuille_ne_liste_que_mes_contrats()
    {
        var (statut, corps) = await Get("/api/contrats", GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal(["AIF-A1", "AIF-A2"], corps.EnumerateArray().Select(c => c.GetProperty("numero_contrat").GetString()));
    }

    [Fact]
    public async Task Portefeuille_pagine_par_limit_et_offset()
    {
        var (_, corps) = await Get("/api/contrats?limit=1&offset=1", GestionnaireA, "Gestionnaire");

        Assert.Equal(["AIF-A2"], corps.EnumerateArray().Select(c => c.GetProperty("numero_contrat").GetString()));
    }

    [Fact]
    public async Task Contrat_porte_exactement_les_dix_huit_champs_dont_les_faits_du_calcul()
    {
        var (statut, corps) = await Get("/api/contrats/AIF-A1", GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal(
            ["anciennete_permis_ans", "anciennete_permis_mois", "crm_bonus_malus", "date_effet", "departement", "formule",
                "mis_a_jour", "nb_sinistres", "nb_sinistres_responsables_trois_ans", "nb_sinistres_trois_ans",
                "numero_contrat", "observations", "puissance_fiscale_cv", "releve_present", "resiliations", "suspensions", "tranche_age", "type_usage"],
            corps.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal));
        Assert.Equal("2026-01-01", corps.GetProperty("date_effet").GetString());
        Assert.Equal(91, corps.GetProperty("anciennete_permis_mois").GetInt32());
    }

    [Fact]
    public async Task Contrat_autre_gestionnaire_et_inexistant_meme_reponse()
    {
        var (statutAutre, autre) = await Get("/api/contrats/AIF-B1", GestionnaireA, "Gestionnaire");
        var (statutInexistant, inexistant) = await Get("/api/contrats/AIF-ZZZ", GestionnaireA, "Gestionnaire");

        Assert.Equal(HttpStatusCode.NotFound, statutAutre);
        Assert.Equal(statutAutre, statutInexistant);
        Assert.Equal("CONTRAT_INTROUVABLE", autre.GetProperty("code").GetString());
        // Seul le traceId varie d'une réponse à l'autre
        Assert.Equal(Sans(autre, "traceId"), Sans(inexistant, "traceId"));
    }

    private static string Sans(JsonElement probleme, string propriete) =>
        string.Join('|', probleme.EnumerateObject().Where(p => p.Name != propriete).Select(p => $"{p.Name}={p.Value}"));

    [Fact]
    public async Task Contrat_sans_role_Gestionnaire_403()
    {
        var (statut, corps) = await Get("/api/contrats/AIF-A1", GestionnaireA, "Telemetrie");

        Assert.Equal(HttpStatusCode.Forbidden, statut);
        Assert.Equal("ACCES_REFUSE", corps.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Portefeuille_sans_role_Gestionnaire_403() =>
        Assert.Equal(HttpStatusCode.Forbidden, (await Get("/api/contrats", GestionnaireA, "Telemetrie")).Statut);

    [Fact]
    public async Task OpenApi_declare_les_deux_routes_et_leurs_erreurs()
    {
        using var client = _usine.CreateClient();
        var doc = JsonDocument.Parse(await client.GetStringAsync(new Uri("/openapi/v1.json", UriKind.Relative), TestContext.Current.CancellationToken)).RootElement;
        var chemins = doc.GetProperty("paths");

        var liste = chemins.GetProperty("/api/contrats").GetProperty("get").GetProperty("responses");
        var unitaire = chemins.GetProperty("/api/contrats/{numero_contrat}").GetProperty("get").GetProperty("responses");

        Assert.Equal(["200", "401", "403"], liste.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal));
        Assert.Equal(["200", "401", "403", "404"], unitaire.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal));
    }
}
