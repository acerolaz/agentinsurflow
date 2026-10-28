using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise;

/// <summary>Une écriture en attente d'une tâche du graphe (valeur opaque).</summary>
public sealed record EcritureEnAttente(string TaskId, int Idx, string Canal, string Type, byte[] Valeur, string TaskPath);

/// <summary>Un point de reprise LangGraph : octets opaques, jamais interprétés ici.</summary>
public sealed record PointDeReprise(
    string ThreadId, string Ns, string CheckpointId, string? ParentId, string Type, byte[] Checkpoint,
    string TypeMetadata, byte[] Metadata, IReadOnlyList<EcritureEnAttente> Ecritures);

/// <summary>Port de stockage des points de reprise du cluster (même sémantique qu'<c>AsyncPostgresSaver</c> : dernier écrit gagnant).</summary>
public interface IDepotPointsDeReprise
{
    /// <summary>Le point <paramref name="checkpointId"/>, ou le dernier du fil si absent, avec ses écritures triées par (task_id, idx).</summary>
    Task<PointDeReprise?> LireAsync(string threadId, string ns, string? checkpointId, CancellationToken ct);

    /// <summary>Les points du fil, <c>checkpoint_id</c> décroissant ; <paramref name="ns"/> absent = tous les espaces de noms.</summary>
    Task<IReadOnlyList<PointDeReprise>> ListerAsync(string threadId, string? ns, string? avant, int? limite, CancellationToken ct);

    /// <summary>Upsert du point sur (thread_id, ns, checkpoint_id) ; ses écritures ne sont pas touchées.</summary>
    Task EcrireAsync(PointDeReprise point, CancellationToken ct);

    /// <summary>Écritures d'une tâche (<paramref name="taskId"/> et <paramref name="taskPath"/> font foi, pas ceux de chaque écriture) : upsert si <c>Idx &lt; 0</c> (écritures spéciales), sinon ignorée si elle existe.</summary>
    Task EcrireEcrituresAsync(
        string threadId, string ns, string checkpointId, string taskId, string taskPath,
        IReadOnlyList<EcritureEnAttente> ecritures, CancellationToken ct);

    /// <summary>Supprime tous les points et écritures du fil.</summary>
    Task SupprimerFilAsync(string threadId, CancellationToken ct);
}

/// <summary>Dépôt EF Core ; upserts en SQL paramétré (valeurs jamais concaténées).</summary>
public sealed class DepotPointsDeRepriseEf(ConnexionsPointsDeReprise connexions) : IDepotPointsDeReprise
{
    private PointsDeRepriseDbContext Contexte() => PointsDeRepriseDbContextFactory.Creer(connexions.PointsDeReprise);

    public async Task<PointDeReprise?> LireAsync(string threadId, string ns, string? checkpointId, CancellationToken ct)
    {
        await using var db = Contexte();
        var points = db.Points.AsNoTracking().Where(x => x.ThreadId == threadId && x.CheckpointNs == ns);
        var ligne = checkpointId is null
            ? await points.OrderByDescending(x => x.CheckpointId).FirstOrDefaultAsync(ct)
            : await points.FirstOrDefaultAsync(x => x.CheckpointId == checkpointId, ct);
        if (ligne is null)
        {
            return null;
        }
        var ecritures = await db.Ecritures.AsNoTracking()
            .Where(x => x.ThreadId == threadId && x.CheckpointNs == ns && x.CheckpointId == ligne.CheckpointId)
            .OrderBy(x => x.TaskId).ThenBy(x => x.Idx)
            .ToListAsync(ct);
        return VersPoint(ligne, ecritures);
    }

    public async Task<IReadOnlyList<PointDeReprise>> ListerAsync(string threadId, string? ns, string? avant, int? limite, CancellationToken ct)
    {
        await using var db = Contexte();
        var points = db.Points.AsNoTracking().Where(x => x.ThreadId == threadId);
        if (ns is not null)
        {
            points = points.Where(x => x.CheckpointNs == ns);
        }
        if (avant is not null)
        {
            points = points.Where(x => x.CheckpointId.CompareTo(avant) < 0);
        }
        points = points.OrderByDescending(x => x.CheckpointId);
        if (limite is { } max)
        {
            points = points.Take(max);
        }
        var lignes = await points.ToListAsync(ct);
        var ids = lignes.ConvertAll(l => l.CheckpointId);
        var ecritures = (await db.Ecritures.AsNoTracking()
            .Where(x => x.ThreadId == threadId && ids.Contains(x.CheckpointId))
            .OrderBy(x => x.TaskId).ThenBy(x => x.Idx)
            .ToListAsync(ct)).ToLookup(x => (x.CheckpointNs, x.CheckpointId));
        return lignes.ConvertAll(l => VersPoint(l, ecritures[(l.CheckpointNs, l.CheckpointId)]));
    }

    public async Task EcrireAsync(PointDeReprise point, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(point);
        await using var db = Contexte();
        await db.Database.ExecuteSqlAsync($"""
            INSERT INTO points_reprise.checkpoint
                (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, type_metadata, metadata)
            VALUES ({point.ThreadId}, {point.Ns}, {point.CheckpointId}, {point.ParentId}, {point.Type}, {point.Checkpoint},
                {point.TypeMetadata}, {point.Metadata})
            ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id) DO UPDATE SET
                parent_checkpoint_id = EXCLUDED.parent_checkpoint_id, type = EXCLUDED.type, checkpoint = EXCLUDED.checkpoint,
                type_metadata = EXCLUDED.type_metadata, metadata = EXCLUDED.metadata
            """, ct);
    }

    public async Task EcrireEcrituresAsync(
        string threadId, string ns, string checkpointId, string taskId, string taskPath,
        IReadOnlyList<EcritureEnAttente> ecritures, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(ecritures);
        await using var db = Contexte();
        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        foreach (var e in ecritures)
        {
            // Écritures spéciales (idx < 0, WRITES_IDX_MAP) : dernier écrit gagnant ; les autres ne s'écrivent qu'une fois
            // (WHERE faux : la ligne existante n'est pas modifiée).
            await db.Database.ExecuteSqlAsync($"""
                INSERT INTO points_reprise.ecriture
                    (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, canal, type, valeur, task_path)
                VALUES ({threadId}, {ns}, {checkpointId}, {taskId}, {e.Idx}, {e.Canal}, {e.Type}, {e.Valeur}, {taskPath})
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) DO UPDATE SET
                    canal = EXCLUDED.canal, type = EXCLUDED.type, valeur = EXCLUDED.valeur, task_path = EXCLUDED.task_path
                WHERE points_reprise.ecriture.idx < 0
                """, ct);
        }
        await transaction.CommitAsync(ct);
    }

    public async Task SupprimerFilAsync(string threadId, CancellationToken ct)
    {
        await using var db = Contexte();
        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        await db.Database.ExecuteSqlAsync($"DELETE FROM points_reprise.ecriture WHERE thread_id = {threadId}", ct);
        await db.Database.ExecuteSqlAsync($"DELETE FROM points_reprise.checkpoint WHERE thread_id = {threadId}", ct);
        await transaction.CommitAsync(ct);
    }

    private static PointDeReprise VersPoint(LignePoint l, IEnumerable<LigneEcriture> ecritures) => new(
        l.ThreadId, l.CheckpointNs, l.CheckpointId, l.ParentCheckpointId, l.Type, l.Checkpoint, l.TypeMetadata, l.Metadata,
        ecritures.Select(e => new EcritureEnAttente(e.TaskId, e.Idx, e.Canal, e.Type, e.Valeur, e.TaskPath)).ToList());
}
