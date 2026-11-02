using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application.Tests;

/// <summary>TU : cas d'usage <see cref="ClasserSansSuite"/>, port <see cref="IDepotRelances"/> simulé.</summary>
public sealed class RelancesTests
{
    private sealed class DepotSimule(SituationRelance? situation, bool figeEntreTemps = false) : IDepotRelances
    {
        public int Ecritures { get; private set; }

        public Task<SituationRelance?> Situation(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult(situation);

        public Task<int?> Ajouter(string gestionnaireId, string numeroContrat, string texte, IReadOnlyList<string> pieces,
            CancellationToken ct) => throw new NotSupportedException();

        public Task<bool> ClasserSansSuite(string gestionnaireId, string numeroContrat, CancellationToken ct)
        {
            Ecritures++;
            return Task.FromResult(!figeEntreTemps);
        }
    }

    private static readonly string[] Manquantes = ["permis"];

    [Theory]
    [InlineData(3, false, false, true, null, 1)]
    [InlineData(3, false, true, false, "DOSSIER_DECIDE", 1)] // figé entre la lecture et l'écriture : le port refuse
    [InlineData(2, false, false, false, "RELANCES_NON_EPUISEES", 0)]
    [InlineData(3, true, false, false, "DOSSIER_DECIDE", 0)]
    public async Task ClasserSansSuite_rend_le_resultat_attendu(int deja, bool decide, bool figeEntreTemps, bool ecrit, string? refus, int ecritures)
    {
        var depot = new DepotSimule(new SituationRelance(deja, decide, Manquantes), figeEntreTemps);

        var r = await new ClasserSansSuite(depot).Executer("A", "C-1", TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(ecrit, refus), r);
        Assert.Equal(ecritures, depot.Ecritures);
    }

    [Fact]
    public async Task ClasserSansSuite_contrat_introuvable_rend_false_sans_code()
    {
        var depot = new DepotSimule(null);

        Assert.Equal(new ResultatEcriture(false, null),
            await new ClasserSansSuite(depot).Executer("A", "C-1", TestContext.Current.CancellationToken));
        Assert.Equal(0, depot.Ecritures);
    }
}
