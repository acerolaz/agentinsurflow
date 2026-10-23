using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>
/// Adapter du port <see cref="IDepotDossiers"/> : lit uniquement la vue minimisée, avec le compte <c>dossiers</c>.
/// Le filtre <c>gestionnaire_id</c> (BOLA) fait partie de chaque requête ; EF paramètre toutes les valeurs.
/// </summary>
internal sealed class DepotDossiersEf(DossiersDbContext db) : IDepotDossiers
{
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
