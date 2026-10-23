using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>
/// Adapter du port <see cref="IDepotEcritures"/> avec le compte <c>dossiers</c> : chaque écriture commence par retrouver
/// le contrat par <c>numero_contrat</c> ET <c>gestionnaire_id</c> (BOLA) ; sans ligne, rien n'est écrit.
/// </summary>
internal sealed class DepotEcrituresEf(DossiersDbContext db, TimeProvider horloge) : IDepotEcritures
{
    private const string Brouillon = "brouillon";

    public async Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
        PrimeBrouillon? prime, CancellationToken ct)
    {
        if (await IdContrat(gestionnaireId, numeroContrat, ct) is not { } contratId) return false;
        var maintenant = horloge.GetUtcNow();

        var decision = await db.Set<Decision>().FirstOrDefaultAsync(d => d.ContratId == contratId && d.EtatValidation == Brouillon, ct);
        if (decision is null)
        {
            decision = new Decision { Id = Guid.NewGuid(), ContratId = contratId, EtatValidation = Brouillon };
            db.Set<Decision>().Add(decision);
        }
        decision.DecisionRendue = fiche.Decision;
        decision.ContratType = fiche.ContratType;
        decision.Score = fiche.Score;
        decision.VersionBareme = fiche.VersionBareme;
        decision.RegleId = string.Join(",", fiche.RegleIds);
        decision.Motifs = JsonSerializer.Serialize(fiche.Motifs);
        decision.Citations = JsonSerializer.Serialize(fiche.Citations);
        decision.Auteur = "agent";
        decision.Horodatage = maintenant;

        if (prime is not null)
        {
            var existante = await db.Set<Prime>().FirstOrDefaultAsync(p => p.ContratId == contratId, ct);
            if (existante is null)
            {
                existante = new Prime { Id = Guid.NewGuid(), ContratId = contratId };
                db.Set<Prime>().Add(existante);
            }
            existante.PrimeTtc = prime.PrimeTtc;
            existante.Periodicite = prime.Periodicite;
            existante.DateEffet = prime.DateEffet;
            existante.EtatValidation = Brouillon;
        }

        await db.SaveChangesAsync(ct);
        return true;
    }

    public async Task<ResultatEcriture> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement,
        CancellationToken ct)
    {
        if (await IdContrat(gestionnaireId, numeroContrat, ct) is not { } contratId) return new(false, null);
        var maintenant = horloge.GetUtcNow();

        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        await db.Set<Contrat>().Where(c => c.Id == contratId).ExecuteUpdateAsync(
            s => s.SetProperty(c => c.Statut, changement.StatutCible).SetProperty(c => c.MisAJour, maintenant), ct);
        if (changement.Validation is not null)
        {
            // La décision finale est le statut cible (ACCEPTE/REFUSE) : CORRIGEE remplace la décision rendue par l'agent.
            var touchees = await db.Set<Decision>().Where(d => d.ContratId == contratId && d.EtatValidation == Brouillon).ExecuteUpdateAsync(
                s => s.SetProperty(d => d.EtatValidation, changement.Validation)
                    .SetProperty(d => d.DecisionRendue, changement.StatutCible)
                    .SetProperty(d => d.Auteur, gestionnaireId)
                    .SetProperty(d => d.Horodatage, maintenant), ct);
            if (touchees == 0)
            {
                await transaction.RollbackAsync(ct);
                return new(false, "DECISION_ABSENTE");
            }
        }
        await transaction.CommitAsync(ct);
        return new(true, null);
    }

    public async Task<string?> StatutContrat(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        await db.Set<Contrat>().AsNoTracking()
            .Where(c => c.NumeroContrat == numeroContrat && c.GestionnaireId == gestionnaireId)
            .Select(c => c.Statut)
            .FirstOrDefaultAsync(ct);

    public async Task<bool> EnregistrerObservations(string gestionnaireId, string numeroContrat, string observations,
        CancellationToken ct)
    {
        var maintenant = horloge.GetUtcNow();
        return await db.Set<Contrat>().Where(c => c.NumeroContrat == numeroContrat && c.GestionnaireId == gestionnaireId)
            .ExecuteUpdateAsync(s => s.SetProperty(c => c.Observations, observations).SetProperty(c => c.MisAJour, maintenant), ct) > 0;
    }

    private async Task<Guid?> IdContrat(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        await db.Set<Contrat>().AsNoTracking()
            .Where(c => c.NumeroContrat == numeroContrat && c.GestionnaireId == gestionnaireId)
            .Select(c => (Guid?)c.Id)
            .FirstOrDefaultAsync(ct);
}
