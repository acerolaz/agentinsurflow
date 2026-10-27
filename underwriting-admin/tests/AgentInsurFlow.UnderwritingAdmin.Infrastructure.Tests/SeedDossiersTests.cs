using AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests;

/// <summary>TU — SQL du seed des gestionnaires C (CI) et du dossier « refus » de A (démo K1), sans base.</summary>
public sealed class SeedDossiersTests
{
    private const string Oid = "33333333-3333-3333-3333-333333333333";

    [Fact]
    public void SqlC_sans_variable_ne_seme_rien() => Assert.Equal("SELECT 1", SeedDossiers.SqlC(null));

    [Fact]
    public void SqlC_seme_trois_dossiers_a_partir_de_7()
    {
        var sql = SeedDossiers.SqlC(Oid);

        Assert.Contains("AIF-2026-000007", sql);
        Assert.Contains("AIF-2026-000009", sql);
        Assert.DoesNotContain("AIF-2026-000010", sql);
        Assert.DoesNotContain("AIF-2026-000001", sql);
        Assert.Contains(Oid, sql);
    }

    [Fact]
    public void SqlC_refuse_un_oid_qui_n_est_pas_un_guid() =>
        Assert.Throws<InvalidOperationException>(() => SeedDossiers.SqlC("x'; DROP TABLE contrat; --"));

    [Fact]
    public void SqlPiecesC_declare_releve_et_permis_des_dossiers_7_a_9()
    {
        var sql = SeedDossiers.SqlPiecesC(Oid);

        Assert.Contains("releve-7.pdf", sql);
        Assert.Contains("permis-9.pdf", sql);
    }

    [Fact]
    public void SqlRefusA_seme_le_dossier_10_avec_une_suspension()
    {
        var sql = SeedDossiers.SqlRefusA(Oid);

        Assert.Contains("AIF-2026-000010", sql);
        Assert.Contains("releve-10.pdf", sql);
        Assert.DoesNotContain("AIF-2026-000007", sql);
    }

    [Fact]
    public void SqlRefusA_sans_variable_ne_seme_rien() => Assert.Equal("SELECT 1", SeedDossiers.SqlRefusA(" "));
}
