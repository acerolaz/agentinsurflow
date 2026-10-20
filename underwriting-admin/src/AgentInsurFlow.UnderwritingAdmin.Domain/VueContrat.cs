namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>
/// Vue minimisée d'un contrat (D39) : aucune donnée directement identifiante. Les noms JSON (snake_case)
/// sont ceux que lit <c>rag</c> ; ne pas les changer sans toucher son client.
/// </summary>
public sealed record VueContrat(
    string NumeroContrat,
    string TrancheAge,
    int AnciennetePermisAns,
    string Departement,
    double CrmBonusMalus,
    int NbSinistres,
    int Suspensions,
    int Resiliations,
    string Formule,
    DateTimeOffset MisAJour);
