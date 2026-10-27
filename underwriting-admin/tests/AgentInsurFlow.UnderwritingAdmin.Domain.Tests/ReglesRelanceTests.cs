namespace AgentInsurFlow.UnderwritingAdmin.Domain.Tests;

/// <summary>
/// TU : une relance de pièces manquantes (D75) — trois au plus, sur un dossier non décidé, pour des pièces que l'agent
/// Pièces a réellement trouvées manquantes, avec un texte borné et stockable.
/// </summary>
public sealed class ReglesRelanceTests
{
    private static readonly string[] Manquantes = ["releve_information", "permis"];

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
        { 0, "Bonjour", [null!], "PIECES_INVALIDES" },
        { 0, "Bonjour", ["carte_grise"], "PIECES_INVALIDES" }, // bien formée mais pas manquante
        // refusés par PostgreSQL (0x00) ou par l'encodage UTF-8 (substitut isolé) : 400, pas 500
        { 0, "a\0b", ["permis"], "TEXTE_INVALIDE" },
        { 0, "a\ud800b", ["permis"], "TEXTE_INVALIDE" },
        { 0, "Bonjour 🚗", ["permis"], null },
    };

    [Theory]
    [MemberData(nameof(Cas))]
    public void Refus(int dejaEnvoyees, string texte, string[] pieces, string? attendu) =>
        Assert.Equal(attendu, ReglesRelance.Refus(new SituationRelance(dejaEnvoyees, false, Manquantes), texte, pieces));

    [Fact]
    public void Dossier_decide_refuse_avant_le_texte() =>
        Assert.Equal("DOSSIER_DECIDE", ReglesRelance.Refus(new SituationRelance(0, true, Manquantes), "", ["permis"]));

    [Fact]
    public void Aucune_piece_manquante_aucune_relance() =>
        Assert.Equal("PIECES_INVALIDES", ReglesRelance.Refus(new SituationRelance(0, false, []), "Bonjour", ["permis"]));

    [Fact]
    public void Trois_relances_au_plus() => Assert.Equal(3, ReglesRelance.Max);
}
