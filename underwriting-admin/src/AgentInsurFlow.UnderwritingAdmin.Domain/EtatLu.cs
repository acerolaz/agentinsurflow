namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Rapport d'un agent tel que le lit l'espace gestionnaire : jamais son contenu, seulement son déroulé.</summary>
public sealed record RapportLu(string Agent, string Mode, string? Cause, string TraceId, DateTimeOffset CreeLe);

/// <summary>
/// État du dossier pour la progression de l'espace gestionnaire (tentative courante). <c>Sections</c> : nom → document JSON
/// déjà sérialisé. Un contrat jamais évalué a un état vide (<c>StatutParcours</c> nul, tentative 0).
/// </summary>
public sealed record EtatLu(string? StatutParcours, int Tentative, int NbRelances,
    IReadOnlyList<RapportLu> Rapports, IReadOnlyDictionary<string, string> Sections);
