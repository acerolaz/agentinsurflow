namespace AgentInsurFlow.UnderwritingAdmin.Domain.Tests;

/// <summary>TU : une relance de pièces manquantes (D75) — trois au plus, texte borné, types de pièces sûrs.</summary>
public sealed class ReglesRelanceTests
{
    public static TheoryData<int, string, string[], string?> Cas => new()
    {
        { 0, "Bonjour", ["permis"], null },
        { 2, "Bonjour", ["releve_information", "permis"], null },
        { 3, "Bonjour", ["permis"], "RELANCES_EPUISEES" },
        { 0, "  ", ["permis"], "TEXTE_INVALIDE" },
        { 0, new string('a', 4001), ["permis"], "TEXTE_INVALIDE" },
        { 0, new string('a', 4000), ["permis"], null },
        { 0, "Bonjour", [], "PIECES_INVALIDES" },
        { 0, "Bonjour", ["Permis!"], "PIECES_INVALIDES" },
        { 0, "Bonjour", [new string('a', 41)], "PIECES_INVALIDES" },
    };

    [Theory]
    [MemberData(nameof(Cas))]
    public void Refus(int dejaEnvoyees, string texte, string[] pieces, string? attendu) =>
        Assert.Equal(attendu, ReglesRelance.Refus(dejaEnvoyees, texte, pieces));

    [Fact]
    public void Trois_relances_au_plus() => Assert.Equal(3, ReglesRelance.Max);
}
