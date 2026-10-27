namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>
/// Contrat généré après ACCEPTE (#101) : conditions particulières (décision validée, prime, formule, parties au contrat).
/// Exception assumée à la minimisation : le contrat imprimé nomme le souscripteur et son véhicule, mais jamais de quoi le
/// contacter (ni e-mail ni téléphone), et seulement une fois le contrat accepté.
/// <see cref="ValidePar"/> est l'oid de l'auteur de la validation, pas un nom ; les montants restent des chaînes (calcul en décimal).
/// </summary>
public sealed record ContratGenere(string NumeroContrat, string Formule, string ContratType, DateOnly DateEffet,
    string PrimeTtcAnnuelle, string PrimeMensuelle, string VersionBareme, string VersionFormule,
    IReadOnlyList<string> Motifs, IReadOnlyList<string> Citations, string ValidePar, DateTimeOffset ValideLe,
    SouscripteurContrat Souscripteur, VehiculeContrat? Vehicule, double CrmBonusMalus);

public sealed record SouscripteurContrat(string Nom, string Prenom, DateOnly DateNaissance, string Adresse, string CodePostal,
    string PermisNumero, DateOnly PermisDateObtention);

public sealed record VehiculeContrat(string Marque, string Modele, string Immatriculation, int PuissanceFiscaleCv, string TypeUsage);
