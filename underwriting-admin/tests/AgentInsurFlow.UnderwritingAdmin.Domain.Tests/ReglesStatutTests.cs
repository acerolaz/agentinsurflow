namespace AgentInsurFlow.UnderwritingAdmin.Domain.Tests;

/// <summary>TU : règles pures du changement de statut d'un dossier.</summary>
public sealed class ReglesStatutTests
{
    [Theory]
    [InlineData("ACCEPTE", null, "VALIDATION_EXIGEE")]
    [InlineData("REFUSE", "VALIDEE", null)]
    [InlineData("ACCEPTE", "CORRIGEE", null)]
    [InlineData("EN_ANALYSE", "VALIDEE", "VALIDATION_INATTENDUE")]
    [InlineData("REVUE_HUMAINE", null, null)]
    [InlineData("REVUE_HUMAINE", "VALIDEE", "VALIDATION_INATTENDUE")]
    [InlineData("ACCEPTE", "OK", "VALIDATION_INCONNUE")]
    [InlineData("actif", null, "STATUT_INCONNU")]
    public void Refus_rend_le_code_attendu(string cible, string? validation, string? attendu) =>
        Assert.Equal(attendu, ReglesStatut.Refus(cible, validation));
}
