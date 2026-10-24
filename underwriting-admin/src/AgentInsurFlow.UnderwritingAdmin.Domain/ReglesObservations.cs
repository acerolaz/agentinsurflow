namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Règles pures des observations du gestionnaire : écrites tant que le statut n'est pas figé (ACCEPTE/REFUSE).</summary>
public static class ReglesObservations
{
    public const int LongueurMax = 2000;

    /// <summary><c>null</c> si l'écriture est acceptée, sinon le code de refus.</summary>
    public static string? Refus(string statutContrat, string observations)
    {
        if (ReglesStatut.Fige(statutContrat)) return "STATUT_FIGE";
        return observations.Length > LongueurMax ? "OBSERVATIONS_TROP_LONGUES" : null;
    }
}
