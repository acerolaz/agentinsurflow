using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise;

/// <summary>
/// Schéma <c>points_reprise</c> de la base <c>dossiers</c> : points de reprise LangGraph, stockés tels quels (octets opaques).
/// Le schéma et les droits du compte <c>points_reprise</c> viennent d'<c>init.sh</c> ; les tables, de la migration (compte <c>migrateur</c>).
/// </summary>
public sealed class PointsDeRepriseDbContext(DbContextOptions<PointsDeRepriseDbContext> options) : DbContext(options)
{
    internal const string Schema = "points_reprise";

    internal DbSet<LignePoint> Points => Set<LignePoint>();

    internal DbSet<LigneEcriture> Ecritures => Set<LigneEcriture>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        ArgumentNullException.ThrowIfNull(modelBuilder);
        modelBuilder.HasDefaultSchema(Schema);

        // Identifiants comparés octet à octet (collation « C ») : l'ordre de checkpoint_id ne dépend pas de la locale du serveur.
        modelBuilder.Entity<LignePoint>(e =>
        {
            e.ToTable("checkpoint");
            e.HasKey(x => new { x.ThreadId, x.CheckpointNs, x.CheckpointId });
            e.Property(x => x.CheckpointId).UseCollation("C");
            e.Property(x => x.ParentCheckpointId).UseCollation("C");
        });
        modelBuilder.Entity<LigneEcriture>(e =>
        {
            e.ToTable("ecriture");
            e.HasKey(x => new { x.ThreadId, x.CheckpointNs, x.CheckpointId, x.TaskId, x.Idx });
            e.Property(x => x.CheckpointId).UseCollation("C");
            e.Property(x => x.TaskId).UseCollation("C");
        });
    }
}

/// <summary>Ligne de la table <c>checkpoint</c>.</summary>
internal sealed class LignePoint
{
    public string ThreadId { get; set; } = "";
    public string CheckpointNs { get; set; } = "";
    public string CheckpointId { get; set; } = "";
    public string? ParentCheckpointId { get; set; }
    public string Type { get; set; } = "";
    public byte[] Checkpoint { get; set; } = [];
    public string TypeMetadata { get; set; } = "";
    public byte[] Metadata { get; set; } = [];
}

/// <summary>Ligne de la table <c>ecriture</c> (écritures en attente d'une tâche).</summary>
internal sealed class LigneEcriture
{
    public string ThreadId { get; set; } = "";
    public string CheckpointNs { get; set; } = "";
    public string CheckpointId { get; set; } = "";
    public string TaskId { get; set; } = "";
    public int Idx { get; set; }
    public string Canal { get; set; } = "";
    public string Type { get; set; } = "";
    public byte[] Valeur { get; set; } = [];
    public string TaskPath { get; set; } = "";
}
