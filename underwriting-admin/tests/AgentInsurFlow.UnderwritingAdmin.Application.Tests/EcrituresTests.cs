using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application.Tests;

/// <summary>TU : cas d'usage d'écriture, avec un port <see cref="IDepotEcritures"/> simulé.</summary>
public sealed class EcrituresTests
{
    private sealed class DepotSimule(bool resultat) : IDepotEcritures
    {
        public int Appels { get; private set; }

        public Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
            PrimeBrouillon? prime, CancellationToken ct)
        {
            Appels++;
            return Task.FromResult(resultat);
        }

        public string? DernierStatut { get; private set; }

        public Task<ResultatEcriture> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
            CancellationToken ct)
        {
            Appels++;
            DernierStatut = $"{gestionnaireId} {numeroContrat} {changement.StatutCible} {changement.Validation}";
            return Task.FromResult(new ResultatEcriture(resultat, null));
        }

        public Task<string?> StatutContrat(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            throw new NotSupportedException();

        public Task<bool> EnregistrerObservations(string gestionnaireId, string numeroContrat, string observations,
            CancellationToken ct) => throw new NotSupportedException();
    }

    private static FicheBrouillon Fiche(string decision = "ACCEPTE") =>
        new(decision, "tous_risques", 0.9m, "v1", ["R1"], ["motif"], ["cit"]);

    private static PrimeBrouillon Prime(string periodicite) => new(42m, periodicite, new DateOnly(2026, 1, 1));

    [Fact]
    public async Task ChangerStatut_sans_validation_n_appelle_pas_le_depot()
    {
        var depot = new DepotSimule(true);
        var r = await new ChangerStatut(depot).Executer("A", "C-1", new ChangementStatut("ACCEPTE", null),
            TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(false, "VALIDATION_EXIGEE"), r);
        Assert.Equal(0, depot.Appels);
    }

    [Fact]
    public async Task ChangerStatut_contrat_introuvable_rend_Ecrit_false_sans_code()
    {
        var r = await new ChangerStatut(new DepotSimule(false)).Executer("A", "C-1",
            new ChangementStatut("ACCEPTE", "VALIDEE"), TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(false, null), r);
    }

    [Fact]
    public async Task ChangerStatut_transmet_au_port_numero_changement_et_gestionnaire()
    {
        var depot = new DepotSimule(true);
        await new ChangerStatut(depot).Executer("A", "C-1", new ChangementStatut("REFUSE", "CORRIGEE"),
            TestContext.Current.CancellationToken);

        Assert.Equal("A C-1 REFUSE CORRIGEE", depot.DernierStatut);
    }

    [Fact]
    public async Task ChangerStatut_relaie_le_refus_du_port()
    {
        var r = await new ChangerStatut(new RefusSimule()).Executer("A", "C-1", new ChangementStatut("ACCEPTE", "VALIDEE"),
            TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(false, "DECISION_ABSENTE"), r);
    }

    private sealed class RefusSimule : IDepotEcritures
    {
        public Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
            PrimeBrouillon? prime, CancellationToken ct) => throw new NotSupportedException();

        public Task<ResultatEcriture> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
            CancellationToken ct) => Task.FromResult(new ResultatEcriture(false, "DECISION_ABSENTE"));

        public Task<string?> StatutContrat(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            throw new NotSupportedException();

        public Task<bool> EnregistrerObservations(string gestionnaireId, string numeroContrat, string observations,
            CancellationToken ct) => throw new NotSupportedException();
    }

    [Fact]
    public async Task ChangerStatut_valide_ecrit()
    {
        var r = await new ChangerStatut(new DepotSimule(true)).Executer("A", "C-1",
            new ChangementStatut("REVUE_HUMAINE", null), TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(true, null), r);
    }

    [Fact]
    public async Task EnregistrerBrouillon_decision_inconnue_refusee()
    {
        var depot = new DepotSimule(true);
        var r = await new EnregistrerBrouillon(depot).Executer("A", "C-1", Fiche("PEUTETRE"), null,
            TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(false, "DECISION_INCONNUE"), r);
        Assert.Equal(0, depot.Appels);
    }

    [Fact]
    public async Task EnregistrerBrouillon_periodicite_inconnue_refusee()
    {
        var depot = new DepotSimule(true);
        var r = await new EnregistrerBrouillon(depot).Executer("A", "C-1", Fiche(), Prime("hebdo"),
            TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(false, "PERIODICITE_INCONNUE"), r);
        Assert.Equal(0, depot.Appels);
    }

    [Fact]
    public async Task EnregistrerBrouillon_valide_ecrit_et_introuvable_rend_false()
    {
        var ct = TestContext.Current.CancellationToken;

        Assert.Equal(new ResultatEcriture(true, null),
            await new EnregistrerBrouillon(new DepotSimule(true)).Executer("A", "C-1", Fiche(), Prime("mensuelle"), ct));
        Assert.Equal(new ResultatEcriture(false, null),
            await new EnregistrerBrouillon(new DepotSimule(false)).Executer("A", "C-1", Fiche(), null, ct));
    }
}
