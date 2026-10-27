namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>
/// Contrat généré après ACCEPTE (#101) : conditions particulières (décision validée, prime, formule, parties au contrat,
/// garanties). Exception assumée à la minimisation (modèle de contrat d'Acerola, 27/10) : le contrat imprimé nomme le
/// souscripteur, ses coordonnées et son véhicule, et seulement une fois le contrat accepté.
/// <see cref="ValidePar"/> est l'oid de l'auteur de la validation, pas un nom ; les montants restent des chaînes (calcul en décimal).
/// </summary>
public sealed record ContratGenere(string NumeroContrat, string Formule, string ContratType, DateOnly DateEffet,
    string PrimeTtcAnnuelle, string PrimeMensuelle, string VersionBareme, string VersionFormule,
    IReadOnlyList<string> Motifs, IReadOnlyList<string> Citations, string ValidePar, DateTimeOffset ValideLe,
    SouscripteurContrat Souscripteur, VehiculeContrat? Vehicule, double CrmBonusMalus, IReadOnlyList<GarantieContrat> Garanties);

public sealed record SouscripteurContrat(string Nom, string Prenom, DateOnly DateNaissance, string Adresse, string CodePostal,
    string PermisNumero, DateOnly PermisDateObtention, string Telephone, string Email, string PermisPays);

public sealed record VehiculeContrat(string Marque, string Modele, string Immatriculation, int PuissanceFiscaleCv, string TypeUsage,
    string Version, string Vin, DateOnly DateMiseCirculation, string ModeStationnement, string CodePostalStationnement);

/// <summary>Garantie souscrite ; <see cref="Franchise"/> null = sans franchise (assistance, par exemple).</summary>
public sealed record GarantieContrat(string Type, decimal? Franchise);
