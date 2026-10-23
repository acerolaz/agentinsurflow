namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

// Entités de persistance du MCD (spec §2.2) ; le Domain n'en connaît aucune. Les types ne servant pas en V1
// (conducteur, pièces, signalement, décision…) existent et restent vides jusqu'aux agents du S4.

internal sealed class Souscripteur
{
    public Guid Id { get; set; }
    public string Nom { get; set; } = "";
    public string Prenom { get; set; } = "";
    public DateOnly DateNaissance { get; set; }
    public string Adresse { get; set; } = "";
    public string Email { get; set; } = "";
    public string Telephone { get; set; } = "";
    public string SituationFamiliale { get; set; } = "";
    public string PermisNumero { get; set; } = "";
    public DateOnly PermisDateObtention { get; set; }
    public string PermisPays { get; set; } = "FR";

    /// <summary>Écart S3-8 au MCD : sert à tirer le département de la vue.</summary>
    public string CodePostal { get; set; } = "";
}

internal sealed class ConducteurSecondaire
{
    public Guid Id { get; set; }
    public Guid SouscripteurId { get; set; }
    public string Identite { get; set; } = "";
    public string LienParente { get; set; } = "";
    public string HistoriquePermis { get; set; } = "";
}

internal sealed class Contrat
{
    public Guid Id { get; set; }

    /// <summary>Écart S3-7 : clé pivot avec rag (<c>CONTRAT.numero</c> du MCD), UNIQUE.</summary>
    public string NumeroContrat { get; set; } = "";
    public Guid SouscripteurId { get; set; }

    /// <summary>oid Entra du gestionnaire propriétaire : contrôle BOLA.</summary>
    public string GestionnaireId { get; set; } = "";
    public DateOnly DateEffet { get; set; }
    public string Statut { get; set; } = "";
    public string Formule { get; set; } = "";
    public DateTimeOffset MisAJour { get; set; }

    /// <summary>Observations libres du gestionnaire (≤ 2000 caractères), écrasées à chaque écriture.</summary>
    public string? Observations { get; set; }
}

internal sealed class Vehicule
{
    public Guid Id { get; set; }
    public Guid ContratId { get; set; }
    public string Immatriculation { get; set; } = "";
    public string Vin { get; set; } = "";
    public string Marque { get; set; } = "";
    public string Modele { get; set; } = "";
    public string Version { get; set; } = "";
    public int PuissanceFiscaleCv { get; set; }
    public int PuissanceDin { get; set; }
    public string Carburant { get; set; } = "";
    public DateOnly Date1reMiseCirculation { get; set; }
    public string TypeUsage { get; set; } = "";
    public int KmAnnuelEstime { get; set; }
    public string ModeStationnement { get; set; } = "";
    public string CodePostalStationnement { get; set; } = "";
}

internal sealed class ReleveInformation
{
    public Guid Id { get; set; }
    public Guid ContratId { get; set; }
    public decimal CrmBonusMalus { get; set; }
    public int NbSuspensionsPermis { get; set; }
    public int NbResiliations { get; set; }
}

internal sealed class Sinistre
{
    public Guid Id { get; set; }
    public Guid ReleveInformationId { get; set; }
    public DateOnly DateSinistre { get; set; }
    public string Nature { get; set; } = "";
    public decimal TauxResponsabilite { get; set; }
}

internal sealed class Garantie
{
    public Guid Id { get; set; }
    public Guid ContratId { get; set; }
    public string Type { get; set; } = "";
    public string Formule { get; set; } = "";
    public decimal PlafondIndemnisation { get; set; }
}

internal sealed class Franchise
{
    public Guid Id { get; set; }
    public Guid GarantieId { get; set; }
    public string GarantieLiee { get; set; } = "";
    public decimal Montant { get; set; }
}

/// <summary>P18 (Acerola) : une prime par contrat (1 → 1), avec montant, périodicité et date d'effet.</summary>
internal sealed class Prime
{
    public Guid Id { get; set; }
    public Guid ContratId { get; set; }
    public decimal PrimePure { get; set; }
    public decimal TaxeFiscale { get; set; }
    public decimal ContributionFgao { get; set; }
    public decimal TaxeAttentatsFgti { get; set; }
    public decimal FraisDossier { get; set; }
    public decimal Remises { get; set; }
    public decimal Surprimes { get; set; }
    public decimal PrimeHt { get; set; }

    /// <summary>Le montant de la prime.</summary>
    public decimal PrimeTtc { get; set; }

    /// <summary><c>mensuelle</c> ou <c>annuelle</c>.</summary>
    public string Periodicite { get; set; } = "annuelle";
    public DateOnly DateEffet { get; set; }

    /// <summary>Brouillon d'un agent tant qu'un gestionnaire ne l'a pas validé.</summary>
    public string EtatValidation { get; set; } = "brouillon";
}

internal sealed class PieceJustificative
{
    public Guid Id { get; set; }
    public Guid ContratId { get; set; }
    public string Type { get; set; } = "";
    public string NomFichier { get; set; } = "";
    public string UrlBlob { get; set; } = "";

    /// <summary>Date d'émission de la pièce (ex. du relevé d'information), lue par l'agent Pièces.</summary>
    public DateOnly DateEmission { get; set; }
    public DateTimeOffset DeclareeLe { get; set; }

    /// <summary>Identifiant (oid) de l'auteur de la déclaration : jamais exposé par l'API.</summary>
    public string DeclareePar { get; set; } = "";
}

internal sealed class SignalementFraude
{
    public Guid Id { get; set; }
    public Guid ContratId { get; set; }
    public string Motif { get; set; } = "";
    public DateTimeOffset SignaleLe { get; set; }
    public string Statut { get; set; } = "ouvert";
}

internal sealed class Decision
{
    public Guid Id { get; set; }
    public Guid ContratId { get; set; }
    public string DecisionRendue { get; set; } = "";
    public string ContratType { get; set; } = "";
    public decimal Score { get; set; }
    public string VersionBareme { get; set; } = "";
    public string RegleId { get; set; } = "";

    /// <summary>JSON (jsonb).</summary>
    public string Motifs { get; set; } = "[]";

    /// <summary>JSON (jsonb) : citations des textes réglementaires.</summary>
    public string Citations { get; set; } = "[]";
    public string EtatValidation { get; set; } = "brouillon";
    public string Auteur { get; set; } = "";
    public DateTimeOffset Horodatage { get; set; }
}

/// <summary>Ligne de la vue <c>vue_contrat_minimisee</c> : seule table que lit le compte <c>dossiers</c>.</summary>
internal sealed class LigneVue
{
    public string NumeroContrat { get; set; } = "";
    public string GestionnaireId { get; set; } = "";
    public string TrancheAge { get; set; } = "";
    public int AnciennetePermisAns { get; set; }
    public string Departement { get; set; } = "";
    public double CrmBonusMalus { get; set; }
    public int NbSinistres { get; set; }
    public int Suspensions { get; set; }
    public int Resiliations { get; set; }
    public string Formule { get; set; } = "";
    public DateTimeOffset MisAJour { get; set; }
    public DateOnly DateEffet { get; set; }
    public int? AnciennetePermisMois { get; set; }
    public int? PuissanceFiscaleCv { get; set; }
    public string? TypeUsage { get; set; }
    public int NbSinistresTroisAns { get; set; }
    public int NbSinistresResponsablesTroisAns { get; set; }
    public bool RelevePresent { get; set; }
    public string? Observations { get; set; }
}

// Mémoire long terme du dossier (D100) : aucune colonne identifiante (nom, adresse…), la liste blanche des sections y veille.

/// <summary>État courant du parcours d'un dossier (une ligne par contrat, clé étrangère vers `contrat.numero_contrat`).</summary>
internal sealed class EtatDossier
{
    public string NumeroContrat { get; set; } = "";
    public int VersionSchema { get; set; } = 1;
    public string StatutParcours { get; set; } = "";
    public int Tentative { get; set; }
    public int NbRelances { get; set; }
    public DateTimeOffset MajLe { get; set; }
}

internal sealed class SectionEtat
{
    public string NumeroContrat { get; set; } = "";
    public string Section { get; set; } = "";
    public int Tentative { get; set; }

    /// <summary>JSON (jsonb).</summary>
    public string Contenu { get; set; } = "{}";
}

/// <summary>Rapport d'un agent : append-only, unique par (contrat, agent, tentative, trace).</summary>
internal sealed class RapportAgent
{
    public string NumeroContrat { get; set; } = "";
    public string Agent { get; set; } = "";
    public int Tentative { get; set; }

    /// <summary>JSON (jsonb).</summary>
    public string Rapport { get; set; } = "{}";
    public string Mode { get; set; } = "";
    public string? Cause { get; set; }
    public string VersionPrompt { get; set; } = "";
    public string TraceId { get; set; } = "";
    public DateTimeOffset CreeLe { get; set; }
}

internal sealed class TourPilotage
{
    public string NumeroContrat { get; set; } = "";
    public int Tentative { get; set; }
    public int Tour { get; set; }
    public string OutilAppele { get; set; } = "";
    public string Precondition { get; set; } = "";
    public string Mode { get; set; } = "";
}
