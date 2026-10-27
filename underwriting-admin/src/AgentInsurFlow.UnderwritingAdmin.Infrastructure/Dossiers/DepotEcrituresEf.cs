using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>
/// Adapter du port <see cref="IDepotEcritures"/> avec le compte <c>dossiers</c> : chaque écriture commence par retrouver
/// le contrat par <c>numero_contrat</c> ET <c>gestionnaire_id</c> (BOLA) ; sans ligne, rien n'est écrit.
/// </summary>
internal sealed class DepotEcrituresEf(DossiersDbContext db, TimeProvider horloge) : IDepotEcritures, IDepotRelances
{
    private const string Brouillon = "brouillon";

    public async Task<SituationRelance?> Situation(string gestionnaireId, string numeroContrat, CancellationToken ct)
    {
        var statut = await db.Set<Contrat>().AsNoTracking()
            .Where(c => c.NumeroContrat == numeroContrat && c.GestionnaireId == gestionnaireId)
            .Select(c => c.Statut)
            .FirstOrDefaultAsync(ct);
        if (statut is null) return null;
        var deja = await db.Set<Relance>().AsNoTracking().CountAsync(r => r.NumeroContrat == numeroContrat, ct);
        // Section « pieces » de la tentative courante (celle de etat_dossier) : ce que l'agent Pièces a trouvé manquant.
        var pieces = await db.Set<SectionEtat>().AsNoTracking()
            .Where(s => s.NumeroContrat == numeroContrat && s.Section == "pieces"
                && db.Set<EtatDossier>().Any(e => e.NumeroContrat == numeroContrat && e.Tentative == s.Tentative))
            .Select(s => s.Contenu)
            .FirstOrDefaultAsync(ct);
        return new SituationRelance(deja, statut is "ACCEPTE" or "REFUSE", Manquantes(pieces));
    }

    private static List<string> Manquantes(string? section)
    {
        if (section is null) return [];
        using var json = JsonDocument.Parse(section);
        var racine = json.RootElement;
        return racine.TryGetProperty("statut", out var s) && s.ValueKind == JsonValueKind.String && s.GetString() == "incomplet"
            && racine.TryGetProperty("manquantes", out var m) && m.ValueKind == JsonValueKind.Array
            ? [.. m.EnumerateArray().Where(p => p.ValueKind == JsonValueKind.String).Select(p => p.GetString()!)]
            : [];
    }

    public async Task<int?> Ajouter(string gestionnaireId, string numeroContrat, string texte, IReadOnlyList<string> pieces, CancellationToken ct)
    {
        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        var rang = await db.Set<Relance>().CountAsync(r => r.NumeroContrat == numeroContrat, ct) + 1;
        var json = JsonSerializer.Serialize(pieces);
        try
        {
            await db.Database.ExecuteSqlAsync($"""
                INSERT INTO relance (numero_contrat, rang, texte, pieces, envoyee_le, envoyee_par)
                VALUES ({numeroContrat}, {rang}, {texte}, {json}::jsonb, {horloge.GetUtcNow()}, {gestionnaireId})
                """, ct);
        }
        catch (PostgresException e) when (e.SqlState == PostgresErrorCodes.UniqueViolation)
        {
            return null; // un envoi simultané a pris ce rang ; la transaction est annulée
        }
        // Compteur de la mémoire du dossier (D100), s'il existe déjà : jamais créé ici.
        await db.Database.ExecuteSqlAsync($"UPDATE etat_dossier SET nb_relances = {rang} WHERE numero_contrat = {numeroContrat}", ct);
        await transaction.CommitAsync(ct);
        return rang;
    }

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

    public async Task<bool> EnregistrerEtat(string gestionnaireId, string numeroContrat, EtatEntrant etat, CancellationToken ct)
    {
        if (await IdContrat(gestionnaireId, numeroContrat, ct) is null) return false;
        var maintenant = horloge.GetUtcNow();

        // Idempotent (la Saga rejoue le même état) : upsert de l'état et des sections, insertion qui ignore un doublon
        // pour les rapports et les tours. Une écriture périmée (tentative plus ancienne) ne remplace pas l'état. nb_relances n'est pas touché ici.
        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        await db.Database.ExecuteSqlAsync($"""
            INSERT INTO etat_dossier (numero_contrat, version_schema, statut_parcours, tentative, nb_relances, maj_le)
            VALUES ({numeroContrat}, 1, {etat.StatutParcours}, {etat.Tentative}, 0, {maintenant})
            ON CONFLICT (numero_contrat) DO UPDATE
            SET statut_parcours = EXCLUDED.statut_parcours, tentative = EXCLUDED.tentative, maj_le = EXCLUDED.maj_le
            WHERE etat_dossier.tentative <= EXCLUDED.tentative
            """, ct);
        foreach (var s in etat.Sections)
            await db.Database.ExecuteSqlAsync($"""
                INSERT INTO section_etat (numero_contrat, section, tentative, contenu)
                VALUES ({numeroContrat}, {s.Section}, {etat.Tentative}, {s.Contenu}::jsonb)
                ON CONFLICT (numero_contrat, section, tentative) DO UPDATE SET contenu = EXCLUDED.contenu
                """, ct);
        foreach (var r in etat.Rapports)
            await db.Database.ExecuteSqlAsync($"""
                INSERT INTO rapport_agent (numero_contrat, agent, tentative, rapport, mode, cause, version_prompt, trace_id)
                VALUES ({numeroContrat}, {r.Agent}, {etat.Tentative}, {r.Rapport}::jsonb, {r.Mode}, {r.Cause}, {r.VersionPrompt}, {r.TraceId})
                ON CONFLICT (numero_contrat, agent, tentative, trace_id) DO NOTHING
                """, ct);
        foreach (var t in etat.Tours)
            await db.Database.ExecuteSqlAsync($"""
                INSERT INTO tour_pilotage (numero_contrat, tentative, tour, outil_appele, precondition, mode)
                VALUES ({numeroContrat}, {etat.Tentative}, {t.Tour}, {t.OutilAppele}, {t.Precondition}, {t.Mode})
                ON CONFLICT (numero_contrat, tentative, tour) DO NOTHING
                """, ct);
        await transaction.CommitAsync(ct);
        return true;
    }

    private async Task<Guid?> IdContrat(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        await db.Set<Contrat>().AsNoTracking()
            .Where(c => c.NumeroContrat == numeroContrat && c.GestionnaireId == gestionnaireId)
            .Select(c => (Guid?)c.Id)
            .FirstOrDefaultAsync(ct);
}
