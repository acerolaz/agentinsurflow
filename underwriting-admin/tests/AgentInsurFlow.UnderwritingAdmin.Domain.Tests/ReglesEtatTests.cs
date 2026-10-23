namespace AgentInsurFlow.UnderwritingAdmin.Domain.Tests;

/// <summary>TU : liste blanche des sections de la mémoire du dossier (D100), aucune donnée identifiante.</summary>
public sealed class ReglesEtatTests
{
    private static EtatEntrant Etat(params string[] sections) =>
        new("EN_COURS", 1, [.. sections.Select(s => new SectionEntrante(s, "{}"))], [], []);

    [Theory]
    [InlineData("dossier")]
    [InlineData("pieces")]
    [InlineData("risque")]
    [InlineData("sources")]
    [InlineData("fiche")]
    [InlineData("prime")]
    [InlineData("validation")]
    [InlineData("pilotage")]
    public void Section_connue_est_acceptee(string section) => Assert.Null(ReglesEtat.Refus(Etat(section)));

    [Fact]
    public void Aucune_section_est_acceptee() => Assert.Null(ReglesEtat.Refus(Etat()));

    [Theory]
    [InlineData("identite")]
    [InlineData("")]
    [InlineData("Dossier")]
    public void Section_inconnue_est_refusee(string section) =>
        Assert.Equal("SECTION_INCONNUE", ReglesEtat.Refus(Etat("risque", section)));
}
