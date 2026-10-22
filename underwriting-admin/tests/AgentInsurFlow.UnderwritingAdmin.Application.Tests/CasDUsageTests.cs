using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application.Tests;

/// <summary>TU : cas d'usage, avec un port <see cref="IDepotDossiers"/> simulé.</summary>
public sealed class CasDUsageTests
{
    private sealed class DepotSimule(params (string Gestionnaire, VueContrat Vue)[] lignes) : IDepotDossiers
    {
        public int DerniereLimite { get; private set; }
        public int DernierDecalage { get; private set; }

        public Task<IReadOnlyList<VueContrat>> Lister(string gestionnaireId, int limit, int offset, CancellationToken ct)
        {
            DerniereLimite = limit;
            DernierDecalage = offset;
            return Task.FromResult<IReadOnlyList<VueContrat>>(
                lignes.Where(l => l.Gestionnaire == gestionnaireId).Select(l => l.Vue).ToList());
        }

        public Task<VueContrat?> Trouver(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(lignes.Where(l => l.Gestionnaire == gestionnaireId && l.Vue.NumeroContrat == numeroContrat)
                .Select(l => l.Vue).FirstOrDefault());
    }

    private static VueContrat Vue(string numero) =>
        new(numero, "25-39", 4, "75", 0.9, 1, 0, 0, "tous_risques", DateTimeOffset.UnixEpoch,
            new DateOnly(2026, 1, 1), 91, 5, "prive", 0, 0);

    [Fact]
    public async Task ConsulterContrat_d_un_autre_gestionnaire_rend_null()
    {
        var cas = new ConsulterContrat(new DepotSimule(("A", Vue("C-1"))));

        Assert.Null(await cas.Executer("B", "C-1", TestContext.Current.CancellationToken));
        Assert.NotNull(await cas.Executer("A", "C-1", TestContext.Current.CancellationToken));
    }

    [Theory]
    [InlineData(1000, 100)]
    [InlineData(0, 1)]
    [InlineData(-5, 1)]
    [InlineData(20, 20)]
    public async Task ListerPortefeuille_borne_limit_a_100(int demande, int attendu)
    {
        var depot = new DepotSimule();

        await new ListerPortefeuille(depot).Executer("A", demande, 0, TestContext.Current.CancellationToken);

        Assert.Equal(attendu, depot.DerniereLimite);
    }

    [Fact]
    public async Task ListerPortefeuille_ramene_un_offset_negatif_a_zero_et_ne_liste_que_les_siens()
    {
        var depot = new DepotSimule(("A", Vue("C-1")), ("B", Vue("C-2")));

        var liste = await new ListerPortefeuille(depot).Executer("A", 10, -3, TestContext.Current.CancellationToken);

        Assert.Equal(0, depot.DernierDecalage);
        Assert.Equal(["C-1"], liste.Select(v => v.NumeroContrat));
    }
}
