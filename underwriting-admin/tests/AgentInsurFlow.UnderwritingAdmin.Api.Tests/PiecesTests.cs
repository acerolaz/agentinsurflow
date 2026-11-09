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

/// <summary>TI : <c>GET /api/v1/contrats/{numero}/pieces</c>, jetons réels, BOLA ; le port <see cref="IDepotDossiers"/> est en mémoire.</summary>
public sealed class PiecesTests : IDisposable
{
    private const string GestionnaireA = "oid-gestionnaire-a";
    private const string GestionnaireB = "oid-gestionnaire-b";

    private sealed class DepotEnMemoire : IDepotDossiers
    {
        public Task<IReadOnlyList<PieceDeclaree>?> ListerPieces(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult<IReadOnlyList<PieceDeclaree>?>(gestionnaireId == GestionnaireA && numeroContrat == "AIF-A1"
                ? [new(TypesPiece.ReleveInformation, new DateOnly(2025, 11, 20)), new(TypesPiece.Permis, new DateOnly(2018, 6, 1))]
                : gestionnaireId == GestionnaireA && numeroContrat == "AIF-A2" ? []
                : null);

        public Task<IReadOnlyList<VueContrat>> Lister(string gestionnaireId, int limit, int offset, CancellationToken ct) =>
            throw new NotSupportedException();

        public Task<VueContrat?> Trouver(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            throw new NotSupportedException();
    }

    private readonly WebApplicationFactory<Program> _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotDossiers>();
        s.AddSingleton<IDepotDossiers, DepotEnMemoire>();
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement Corps)> Get(string numero, string oid)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, $"/api/v1/contrats/{numero}/pieces");
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer",
            JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, "Gestionnaire"));
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var corps = JsonDocument.Parse(await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken)).RootElement.Clone();
        return (reponse.StatusCode, corps);
    }

    [Fact]
    public async Task Pieces_du_contrat_rendent_seulement_type_et_date_emission()
    {
        var (statut, corps) = await Get("AIF-A1", GestionnaireA);

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal(2, corps.GetArrayLength());
        Assert.Equal("releve_information", corps[0].GetProperty("type").GetString());
        Assert.Equal("2025-11-20", corps[0].GetProperty("date_emission").GetString());
        Assert.All(corps.EnumerateArray(), p => Assert.Equal(["date_emission", "type"],
            p.EnumerateObject().Select(x => x.Name).Order(StringComparer.Ordinal).ToArray()));
    }

    [Fact]
    public async Task Contrat_sans_piece_rend_une_liste_vide() =>
        Assert.Equal(0, (await Get("AIF-A2", GestionnaireA)).Corps.GetArrayLength());

    [Fact]
    public async Task Contrat_d_un_autre_gestionnaire_ou_inexistant_rend_le_meme_404()
    {
        var (autre, corpsAutre) = await Get("AIF-A1", GestionnaireB);
        var (absent, corpsAbsent) = await Get("AIF-ZZ", GestionnaireA);

        Assert.Equal(HttpStatusCode.NotFound, autre);
        Assert.Equal(HttpStatusCode.NotFound, absent);
        Assert.Equal("CONTRAT_INTROUVABLE", corpsAutre.GetProperty("code").GetString());
        Assert.Equal(corpsAbsent.GetProperty("code").GetString(), corpsAutre.GetProperty("code").GetString());
    }

    private async Task<HttpResponseMessage> GetFichier(string numero, string type, string oid)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, $"/api/v1/contrats/{numero}/pieces/{type}/fichier");
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer",
            JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, oid, "Gestionnaire"));
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    [Theory]
    [InlineData(TypesPiece.ReleveInformation)]
    [InlineData(TypesPiece.Permis)]
    public async Task Fichier_d_une_piece_declaree_est_un_pdf_embarque(string type)
    {
        using var reponse = await GetFichier("AIF-A1", type, GestionnaireA);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Equal("application/pdf", reponse.Content.Headers.ContentType?.MediaType);
        var octets = await reponse.Content.ReadAsByteArrayAsync(TestContext.Current.CancellationToken);
        Assert.Equal("%PDF-"u8.ToArray(), octets[..5]);
    }

    [Fact]
    public async Task Fichier_du_contrat_d_un_autre_gestionnaire_rend_le_meme_404()
    {
        using var autre = await GetFichier("AIF-A1", TypesPiece.Permis, GestionnaireB);
        using var inexistant = await GetFichier("AIF-INEXISTANT", TypesPiece.Permis, GestionnaireA);

        Assert.Equal(HttpStatusCode.NotFound, autre.StatusCode);
        Assert.Equal(await inexistant.Content.ReadAsStringAsync(TestContext.Current.CancellationToken),
            await autre.Content.ReadAsStringAsync(TestContext.Current.CancellationToken));
    }
}
