namespace AgentInsurFlow.UnderwritingAdmin.Domain.Tests;

/// <summary>TU : règles pures des observations du gestionnaire (statut non figé, 2000 caractères au plus).</summary>
public sealed class ReglesObservationsTests
{
    [Theory]
    [InlineData("BROUILLON", 2000, null)]
    [InlineData("EN_ANALYSE", 1, null)]
    [InlineData("REVUE_HUMAINE", 0, null)]
    [InlineData("actif", 1, null)] // statut du seed : dossier pas encore évalué
    [InlineData("BROUILLON", 2001, "OBSERVATIONS_TROP_LONGUES")]
    [InlineData("ACCEPTE", 1, "STATUT_FIGE")]
    [InlineData("REFUSE", 1, "STATUT_FIGE")]
    public void Refus_rend_le_code_attendu(string statut, int longueur, string? attendu) =>
        Assert.Equal(attendu, ReglesObservations.Refus(statut, new string('a', longueur)));
}
