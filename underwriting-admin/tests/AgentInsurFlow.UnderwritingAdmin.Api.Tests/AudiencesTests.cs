using System.Net;
using Microsoft.AspNetCore.Mvc.Testing;

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>TI : la liste « a, b » d'audiences (convention gateway/rag) est découpée, chaque valeur est acceptée.</summary>
public sealed class AudiencesTests : IDisposable
{
    private readonly WebApplicationFactory<Program> _usine =
        JetonsDeTest.Usine(b => b.UseSetting("Entra:Audiences:underwriting:0", "api://a, api://b"));

    public void Dispose() => _usine.Dispose();

    private async Task<HttpStatusCode> Appeler(string audience)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, "/api/inconnue");
        requete.Headers.Add("Authorization", $"Bearer {JetonsDeTest.Jeton(audience, "oid-a", "Gestionnaire")}");
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        return reponse.StatusCode;
    }

    // Jeton valide : le repli exige seulement un utilisateur authentifié, la route inconnue répond donc 404.
    [Theory]
    [InlineData("api://a")]
    [InlineData("api://b")]
    public async Task Jeton_de_chaque_audience_de_la_liste_est_accepte(string audience) =>
        Assert.Equal(HttpStatusCode.NotFound, await Appeler(audience));

    [Fact]
    public async Task Jeton_d_une_autre_audience_401() =>
        Assert.Equal(HttpStatusCode.Unauthorized, await Appeler("api://c"));
}
