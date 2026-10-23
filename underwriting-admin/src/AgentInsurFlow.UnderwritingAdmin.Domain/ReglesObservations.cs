namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Règles pures des observations du gestionnaire : écrites tant que le statut n'est pas figé (ACCEPTE/REFUSE).</summary>
public static class ReglesObservations
{
    public const int LongueurMax = 2000;

    private static readonly HashSet<string> StatutsModifiables =
        new HashSet<string> { "BROUILLON", "EN_ANALYSE", "REVUE_HUMAINE" };

    /// <summary><c>null</c> si l'écriture est acceptée, sinon le code de refus.</summary>
    public static string? Refus(string statutContrat, string observations)
    {
        if (!StatutsModifiables.Contains(statutContrat)) return "STATUT_FIGE";
        return observations.Length > LongueurMax ? "OBSERVATIONS_TROP_LONGUES" : null;
    }
}
