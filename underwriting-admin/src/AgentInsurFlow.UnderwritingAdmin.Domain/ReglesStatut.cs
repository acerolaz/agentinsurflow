namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Règles pures d'écriture d'un dossier : statuts cibles, validations, décisions, périodicités.</summary>
public static class ReglesStatut
{
    public static readonly IReadOnlySet<string> Cibles =
        new HashSet<string> { "EN_ANALYSE", "REVUE_HUMAINE", "ACCEPTE", "REFUSE" };

    public static readonly IReadOnlySet<string> Validations = new HashSet<string> { "VALIDEE", "CORRIGEE" };

    public static readonly IReadOnlySet<string> Decisions = new HashSet<string> { "ACCEPTE", "REFUSE", "REVUE_HUMAINE" };

    public static readonly IReadOnlySet<string> Periodicites = new HashSet<string> { "mensuelle", "annuelle" };

    /// <summary>Un dossier décidé (ACCEPTE/REFUSE) n'est plus modifiable : la décision humaine n'est pas réversible.</summary>
    public static bool Fige(string statutContrat) => statutContrat is "ACCEPTE" or "REFUSE";

    /// <summary><c>null</c> si le changement est accepté, sinon le code de refus.</summary>
    public static string? Refus(string statutCible, string? validation)
    {
        if (!Cibles.Contains(statutCible)) return "STATUT_INCONNU";
        var final = statutCible is "ACCEPTE" or "REFUSE";
        if (validation is null) return final ? "VALIDATION_EXIGEE" : null;
        if (!Validations.Contains(validation)) return "VALIDATION_INCONNUE";
        return final ? null : "VALIDATION_INATTENDUE";
    }
}

/// <summary>Fiche d'instruction enregistrée en brouillon.</summary>
public sealed record FicheBrouillon(
    string Decision,
    string ContratType,
    decimal Score,
    string VersionBareme,
    IReadOnlyList<string> RegleIds,
    IReadOnlyList<string> Motifs,
    IReadOnlyList<string> Citations);

/// <summary>Prime proposée ; <c>Periodicite</c> ∈ <see cref="ReglesStatut.Periodicites"/>.</summary>
public sealed record PrimeBrouillon(decimal PrimeTtc, string Periodicite, DateOnly DateEffet);

/// <summary>Changement de statut ; avec validation, la décision finale est le statut cible lui-même.</summary>
public sealed record ChangementStatut(string StatutCible, string? Validation);
