using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>
/// Adapter du port <see cref="IDepotDossiers"/> : lit uniquement la vue minimisée, avec le compte <c>dossiers</c>.
/// Le filtre <c>gestionnaire_id</c> (BOLA) fait partie de chaque requête ; EF paramètre toutes les valeurs.
/// </summary>
internal sealed class DepotDossiersEf(DossiersDbContext db) : IDepotDossiers, IDepotEtat, IDepotContratGenere
{
    public async Task<(ContratGenere? Contrat, bool Existe)> LireContratGenere(string gestionnaireId, string numeroContrat, CancellationToken ct)
    {
        var contrat = await db.Set<Contrat>().AsNoTracking()
            .Where(c => c.GestionnaireId == gestionnaireId && c.NumeroContrat == numeroContrat)
            .Select(c => new { c.Id, c.Statut })
            .FirstOrDefaultAsync(ct);
        if (contrat is null) return (null, false);
        if (contrat.Statut != "ACCEPTE") return (null, true);

        var decision = await db.Set<Decision>().AsNoTracking()
            .Where(d => d.ContratId == contrat.Id && d.EtatValidation != "brouillon")
            .OrderByDescending(d => d.Horodatage)
            .FirstOrDefaultAsync(ct);
        var vue = await db.Vue.AsNoTracking()
            .Where(l => l.GestionnaireId == gestionnaireId && l.NumeroContrat == numeroContrat)
            .Select(l => new { l.Formule, l.DateEffet, l.CrmBonusMalus })
            .FirstOrDefaultAsync(ct);
        // Parties au contrat imprimé : vue_contrat_accepte ne rend que les contrats ACCEPTE (BOLA ici aussi).
        var parties = await db.Set<PartiesContratAccepte>().AsNoTracking()
            .Where(p => p.GestionnaireId == gestionnaireId && p.NumeroContrat == numeroContrat)
            .FirstOrDefaultAsync(ct);
        if (decision is null || vue is null || parties is null) return (null, true);

        // Montants et version de formule : section « prime » de la tentative courante (réponse de la Function de calcul).
        var prime = await db.Set<SectionEtat>().AsNoTracking()
            .Where(s => s.NumeroContrat == numeroContrat && s.Section == "prime")
            .OrderByDescending(s => s.Tentative)
            .Select(s => s.Contenu)
            .FirstOrDefaultAsync(ct);
        using var json = JsonDocument.Parse(prime ?? "{}");
        string Champ(string nom) => json.RootElement.TryGetProperty(nom, out var v) ? v.ToString() : "";

        return (new ContratGenere(numeroContrat, vue.Formule, decision.ContratType, vue.DateEffet,
            Champ("prime_ttc_annuelle"), Champ("prime_mensuelle"), decision.VersionBareme, Champ("version_formule"),
            JsonSerializer.Deserialize<List<string>>(decision.Motifs) ?? [], JsonSerializer.Deserialize<List<string>>(decision.Citations) ?? [],
            decision.Auteur, decision.Horodatage,
            new SouscripteurContrat(parties.Nom, parties.Prenom, parties.DateNaissance, parties.Adresse, parties.CodePostal,
                parties.PermisNumero, parties.PermisDateObtention),
            parties.Immatriculation is null ? null : new VehiculeContrat(parties.Marque ?? "", parties.Modele ?? "",
                parties.Immatriculation, parties.PuissanceFiscaleCv ?? 0, parties.TypeUsage ?? ""),
            vue.CrmBonusMalus), true);
    }

    public async Task<EtatLu?> LireEtat(string gestionnaireId, string numeroContrat, CancellationToken ct)
    {
        // BOLA : le contrat est d'abord résolu pour ce gestionnaire.
        var existe = await db.Set<Contrat>().AsNoTracking()
            .AnyAsync(c => c.GestionnaireId == gestionnaireId && c.NumeroContrat == numeroContrat, ct);
        if (!existe) return null;
        var etat = await db.Set<EtatDossier>().AsNoTracking().FirstOrDefaultAsync(e => e.NumeroContrat == numeroContrat, ct);
        // Compteur lu dans la table relance : une relance enregistrée avant le premier état compte aussi.
        var nbRelances = await db.Set<Relance>().AsNoTracking().CountAsync(r => r.NumeroContrat == numeroContrat, ct);
        if (etat is null) return new EtatLu(null, 0, nbRelances, [], new Dictionary<string, string>());
        var rapports = await db.Set<RapportAgent>().AsNoTracking()
            .Where(r => r.NumeroContrat == numeroContrat && r.Tentative == etat.Tentative)
            .OrderBy(r => r.CreeLe)
            .Select(r => new RapportLu(r.Agent, r.Mode, r.Cause, r.TraceId, r.CreeLe))
            .ToListAsync(ct);
        var sections = await db.Set<SectionEtat>().AsNoTracking()
            .Where(s => s.NumeroContrat == numeroContrat && s.Tentative == etat.Tentative)
            .ToDictionaryAsync(s => s.Section, s => s.Contenu, ct);
        return new EtatLu(etat.StatutParcours, etat.Tentative, nbRelances, rapports, sections);
    }

    public async Task<IReadOnlyList<VueContrat>> Lister(string gestionnaireId, int limit, int offset, CancellationToken ct) =>
        await db.Vue.AsNoTracking()
            .Where(l => l.GestionnaireId == gestionnaireId)
            .OrderBy(l => l.NumeroContrat)
            .Skip(offset).Take(limit)
            .Select(l => Vers(l))
            .ToListAsync(ct);

    public async Task<VueContrat?> Trouver(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        await db.Vue.AsNoTracking()
            .Where(l => l.GestionnaireId == gestionnaireId && l.NumeroContrat == numeroContrat)
            .Select(l => Vers(l))
            .FirstOrDefaultAsync(ct);

    public async Task<IReadOnlyList<PieceDeclaree>?> ListerPieces(string gestionnaireId, string numeroContrat, CancellationToken ct)
    {
        // BOLA : le contrat est d'abord résolu pour ce gestionnaire ; le compte `dossiers` ne lit que ces colonnes.
        var contratId = await db.Set<Contrat>().AsNoTracking()
            .Where(c => c.GestionnaireId == gestionnaireId && c.NumeroContrat == numeroContrat)
            .Select(c => (Guid?)c.Id)
            .FirstOrDefaultAsync(ct);
        if (contratId is null) return null;
        return await db.Set<PieceJustificative>().AsNoTracking()
            .Where(p => p.ContratId == contratId)
            .OrderBy(p => p.DateEmission).ThenBy(p => p.Type)
            .Select(p => new PieceDeclaree(p.Type, p.DateEmission))
            .ToListAsync(ct);
    }

    private static VueContrat Vers(LigneVue l) => new(l.NumeroContrat, l.TrancheAge, l.AnciennetePermisAns, l.Departement,
        l.CrmBonusMalus, l.NbSinistres, l.Suspensions, l.Resiliations, l.Formule, l.MisAJour,
        l.DateEffet, l.AnciennetePermisMois, l.PuissanceFiscaleCv, l.TypeUsage, l.NbSinistresTroisAns, l.NbSinistresResponsablesTroisAns,
        l.RelevePresent, l.Observations);
}
