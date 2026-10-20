namespace AgentInsurFlow.UnderwritingAdmin.Domain.Tests;

/// <summary>TU : règles pures de minimisation (D39), sans I/O.</summary>
public sealed class ReglesTests
{
    [Theory]
    [InlineData(18, "<25")]
    [InlineData(24, "<25")]
    [InlineData(25, "25-39")]
    [InlineData(39, "25-39")]
    [InlineData(40, "40-59")]
    [InlineData(59, "40-59")]
    [InlineData(60, "60+")]
    [InlineData(95, "60+")]
    public void Tranche_age(int age, string attendu) => Assert.Equal(attendu, TrancheAge.Depuis(age));

    [Theory]
    [InlineData("75011", "75")]
    [InlineData("97411", "974")]
    [InlineData("98000", "980")]
    [InlineData("2A004", "2A")]
    [InlineData("2B033", "2B")]
    public void Departement_depuis_code_postal(string codePostal, string attendu) =>
        Assert.Equal(attendu, Departement.Depuis(codePostal));

    [Theory]
    [InlineData("")]
    [InlineData("7")]
    public void Departement_refuse_un_code_postal_trop_court(string codePostal) =>
        Assert.Throws<ArgumentException>(() => Departement.Depuis(codePostal));
}
