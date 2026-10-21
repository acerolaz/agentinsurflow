using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Traces;

/// <summary>Base <c>traces</c> : table <c>span</c> au modèle de données OTLP (spec §9.3).</summary>
public sealed class TracesDbContext(DbContextOptions<TracesDbContext> options) : DbContext(options)
{
    internal DbSet<LigneSpan> Spans => Set<LigneSpan>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        ArgumentNullException.ThrowIfNull(modelBuilder);

        modelBuilder.Entity<LigneSpan>(e =>
        {
            e.ToTable("span");
            e.HasKey(x => new { x.TraceId, x.SpanId });
            e.Property(x => x.TraceId).HasColumnType("char(32)");
            e.Property(x => x.SpanId).HasColumnType("char(16)");
            e.Property(x => x.ParentSpanId).HasColumnType("char(16)");
            e.Property(x => x.Kind).HasColumnType("smallint");
            e.Property(x => x.StatusCode).HasColumnType("smallint");
            e.Property(x => x.DureeMs).HasComputedColumnSql("(end_time_unix_nano - start_time_unix_nano) / 1e6", stored: true);
            e.Property(x => x.ResourceAttributes).HasColumnType("jsonb");
            e.Property(x => x.Attributes).HasColumnType("jsonb");
            e.Property(x => x.Events).HasColumnType("jsonb");
            e.Property(x => x.Links).HasColumnType("jsonb");
            e.HasIndex(x => new { x.ServiceName, x.StartTimeUnixNano });
            e.HasIndex(x => x.ParentSpanId);
            e.HasIndex(x => x.Attributes).HasMethod("gin");
        });
    }
}

/// <summary>Ligne de la table <c>span</c>.</summary>
internal sealed class LigneSpan
{
    public string TraceId { get; set; } = "";
    public string SpanId { get; set; } = "";
    public string? ParentSpanId { get; set; }
    public string TraceState { get; set; } = "";
    public string Name { get; set; } = "";
    public short Kind { get; set; } // smallint, comme la migration
    public long StartTimeUnixNano { get; set; }
    public long EndTimeUnixNano { get; set; }
    public double DureeMs { get; set; }
    public short StatusCode { get; set; }
    public string StatusMessage { get; set; } = "";
    public string ServiceName { get; set; } = "";
    public string ResourceAttributes { get; set; } = "{}";
    public string Attributes { get; set; } = "{}";
    public string ScopeName { get; set; } = "";
    public string ScopeVersion { get; set; } = "";
    public string Events { get; set; } = "[]";
    public string Links { get; set; } = "[]";
    public DateTimeOffset RecuLe { get; set; }
}
