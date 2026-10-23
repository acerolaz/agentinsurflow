namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Section de l'état du dossier ; <c>Contenu</c> est un document JSON déjà sérialisé.</summary>
public sealed record SectionEntrante(string Section, string Contenu);

/// <summary>Rapport d'un agent, ajouté une seule fois par (agent, tentative, trace) ; <c>Rapport</c> est un document JSON.</summary>
public sealed record RapportEntrant(string Agent, string Rapport, string Mode, string? Cause, string VersionPrompt, string TraceId);

/// <summary>Un tour de pilotage de l'orchestrateur.</summary>
public sealed record TourEntrant(int Tour, string OutilAppele, string Precondition, string Mode);

/// <summary>État que l'orchestrateur confie à la mémoire long terme du dossier (D100).</summary>
public sealed record EtatEntrant(string StatutParcours, int Tentative, IReadOnlyList<SectionEntrante> Sections,
    IReadOnlyList<RapportEntrant> Rapports, IReadOnlyList<TourEntrant> Tours);

/// <summary>
/// Règle pure de la mémoire du dossier (D100) : seules les sections de la liste blanche sont écrites. Elle ne filtre que
/// le nom de section, pas le contenu : l'absence de donnée identifiante dans <c>contenu</c> reste la responsabilité de l'orchestrateur.
/// </summary>
public static class ReglesEtat
{
    private static readonly HashSet<string> SectionsConnues =
        new HashSet<string> { "dossier", "pieces", "risque", "sources", "fiche", "prime", "validation", "pilotage" };

    /// <summary><c>null</c> si l'état est accepté, sinon le code de refus.</summary>
    public static string? Refus(EtatEntrant etat)
    {
        ArgumentNullException.ThrowIfNull(etat);
        return etat.Sections.All(s => SectionsConnues.Contains(s.Section)) ? null : "SECTION_INCONNUE";
    }
}
