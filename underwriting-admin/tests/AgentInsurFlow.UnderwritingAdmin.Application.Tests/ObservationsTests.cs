using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application.Tests;

/// <summary>TU : cas d'usage <see cref="EnregistrerObservations"/>, port <see cref="IDepotEcritures"/> simulé.</summary>
public sealed class ObservationsTests
{
    private sealed class DepotSimule(string? statut) : IDepotEcritures
    {
        public int Ecritures { get; private set; }

        public Task<string?> StatutContrat(string gestionnaireId, string numeroContrat, CancellationToken ct) => Task.FromResult(statut);

        public Task<bool> EnregistrerObservations(string gestionnaireId, string numeroContrat, string observations, CancellationToken ct)
        {
            Ecritures++;
            return Task.FromResult(true);
        }

        public Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
            PrimeBrouillon? prime, CancellationToken ct) => throw new NotSupportedException();

        public Task<ResultatEcriture> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
            CancellationToken ct) => throw new NotSupportedException();
    }

    [Theory]
    [InlineData(null, false, null, 0)]
    [InlineData("ACCEPTE", false, "STATUT_FIGE", 0)]
    [InlineData("EN_ANALYSE", true, null, 1)]
    public async Task Executer_rend_le_resultat_attendu(string? statut, bool ecrit, string? refus, int ecritures)
    {
        var depot = new DepotSimule(statut);

        var r = await new EnregistrerObservations(depot).Executer("A", "C-1", "note", TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(ecrit, refus), r);
        Assert.Equal(ecritures, depot.Ecritures);
    }
}
