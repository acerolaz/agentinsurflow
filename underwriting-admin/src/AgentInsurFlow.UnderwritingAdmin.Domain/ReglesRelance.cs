using System.Buffers;
using System.Text;
using System.Text.RegularExpressions;

namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>
/// Règle pure d'une relance de pièces manquantes (D75) : trois au plus par dossier, jamais sur un dossier décidé, seulement
/// pour des pièces que l'agent Pièces a trouvées manquantes (identifiants : ils partent dans un span), texte non vide, borné
/// et stockable. Le texte n'est jamais interprété : il est stocké tel quel.
/// </summary>
public static partial class ReglesRelance
{
    public const int Max = 3;
    public const int TexteMax = 4000;
    public const string Epuisees = "RELANCES_EPUISEES";
    public const string Decide = "DOSSIER_DECIDE";
    public const string Concurrente = "RELANCE_CONCURRENTE";

    /// <summary><c>null</c> si la relance est acceptée, sinon le code de refus.</summary>
    public static string? Refus(SituationRelance situation, string texte, IReadOnlyList<string> pieces)
    {
        ArgumentNullException.ThrowIfNull(situation);
        ArgumentNullException.ThrowIfNull(pieces);
        if (situation.Deja >= Max) return Epuisees;
        if (situation.Decide) return Decide;
        if (string.IsNullOrWhiteSpace(texte) || texte.Length > TexteMax || !Stockable(texte)) return "TEXTE_INVALIDE";
        return pieces.Count > 0 && pieces.All(p => p is not null && TypePiece().IsMatch(p) && situation.Manquantes.Contains(p))
            ? null : "PIECES_INVALIDES";
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

/// <summary>
/// Ce qu'une relance doit savoir du dossier : relances déjà enregistrées, statut décidé (ACCEPTE ou REFUSE) et pièces
/// manquantes selon la section <c>pieces</c> de la tentative courante (vide si aucune ou si le dossier est complet).
/// </summary>
public sealed record SituationRelance(int Deja, bool Decide, IReadOnlyList<string> Manquantes);
