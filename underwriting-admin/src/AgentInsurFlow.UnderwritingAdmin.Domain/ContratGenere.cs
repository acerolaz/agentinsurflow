namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>
/// Contrat généré après ACCEPTE (#101) : décision validée, prime et formule, sans aucune donnée identifiante.
/// <see cref="ValidePar"/> est l'oid de l'auteur de la validation, pas un nom ; les montants restent des chaînes (calcul en décimal).
/// </summary>
public sealed record ContratGenere(string NumeroContrat, string Formule, string ContratType, DateOnly DateEffet,
    string PrimeTtcAnnuelle, string PrimeMensuelle, string VersionBareme, string VersionFormule,
    IReadOnlyList<string> Motifs, IReadOnlyList<string> Citations, string ValidePar, DateTimeOffset ValideLe);
