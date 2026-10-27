using System.Buffers;
using System.Text;
using System.Text.RegularExpressions;

namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>
/// Règle pure d'une relance de pièces manquantes (D75) : trois au plus par dossier, texte non vide et borné, types de pièces
/// réduits à des identifiants (ils partent dans un span). Le texte n'est jamais interprété : il est stocké tel quel.
/// </summary>
public static partial class ReglesRelance
{
    public const int Max = 3;
    public const int TexteMax = 4000;
    public const string Epuisees = "RELANCES_EPUISEES";

    /// <summary><c>null</c> si la relance est acceptée, sinon le code de refus.</summary>
    public static string? Refus(int dejaEnvoyees, string texte, IReadOnlyList<string> pieces)
    {
        ArgumentNullException.ThrowIfNull(pieces);
        if (dejaEnvoyees >= Max) return Epuisees;
        if (string.IsNullOrWhiteSpace(texte) || texte.Length > TexteMax || !Stockable(texte)) return "TEXTE_INVALIDE";
        return pieces.Count > 0 && pieces.All(p => p is not null && TypePiece().IsMatch(p)) ? null : "PIECES_INVALIDES";
    }

    /// <summary>Ni NUL (refusé par PostgreSQL) ni substitut isolé (non encodable en UTF-8).</summary>
    private static bool Stockable(string texte)
    {
        var reste = texte.AsSpan();
        while (!reste.IsEmpty)
        {
            if (Rune.DecodeFromUtf16(reste, out var r, out var lus) != OperationStatus.Done || r.Value == 0) return false;
            reste = reste[lus..];
        }
        return true;
    }

    [GeneratedRegex("^[a-z_]{1,40}$")]
    private static partial Regex TypePiece();
}
