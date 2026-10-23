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

    private static VueContrat Vers(LigneVue l) => new(l.NumeroContrat, l.TrancheAge, l.AnciennetePermisAns, l.Departement,
        l.CrmBonusMalus, l.NbSinistres, l.Suspensions, l.Resiliations, l.Formule, l.MisAJour,
        l.DateEffet, l.AnciennetePermisMois, l.PuissanceFiscaleCv, l.TypeUsage, l.NbSinistresTroisAns, l.NbSinistresResponsablesTroisAns,
        l.RelevePresent, l.Observations);
}
