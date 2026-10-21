using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>
/// Base <c>dossiers</c> (MCD Merise, spec §2.2). Le compte <c>migrateur</c> (propriétaire) crée le schéma ;
/// le compte <c>dossiers</c> ne lit que la vue minimisée.
/// </summary>
public sealed class DossiersDbContext(DbContextOptions<DossiersDbContext> options) : DbContext(options)
{
    internal DbSet<LigneVue> Vue => Set<LigneVue>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        ArgumentNullException.ThrowIfNull(modelBuilder);

        // Les clés sont des UUID fournis par l'appelant (le seed en fixe, les agents en généreront).
        modelBuilder.Entity<Souscripteur>(e => e.Property(x => x.Id).ValueGeneratedNever());
        modelBuilder.Entity<ConducteurSecondaire>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<Souscripteur>().WithMany().HasForeignKey(x => x.SouscripteurId);
        });
        modelBuilder.Entity<Contrat>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasIndex(x => x.NumeroContrat).IsUnique();
            e.HasIndex(x => x.GestionnaireId);
            e.HasOne<Souscripteur>().WithOne().HasForeignKey<Contrat>(x => x.SouscripteurId);
        });
        // Relations 1 → 1 avec CONTRAT (MCD) : clé étrangère unique.
        modelBuilder.Entity<Vehicule>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<Contrat>().WithOne().HasForeignKey<Vehicule>(x => x.ContratId);
        });
        modelBuilder.Entity<ReleveInformation>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<Contrat>().WithOne().HasForeignKey<ReleveInformation>(x => x.ContratId);
        });
        modelBuilder.Entity<Prime>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<Contrat>().WithOne().HasForeignKey<Prime>(x => x.ContratId);
            e.Property(x => x.PrimeHt).HasPrecision(12, 2);
            e.Property(x => x.PrimeTtc).HasPrecision(12, 2);
        });
        modelBuilder.Entity<Sinistre>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<ReleveInformation>().WithMany().HasForeignKey(x => x.ReleveInformationId);
        });
        modelBuilder.Entity<Garantie>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<Contrat>().WithMany().HasForeignKey(x => x.ContratId);
        });
        modelBuilder.Entity<Franchise>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<Garantie>().WithOne().HasForeignKey<Franchise>(x => x.GarantieId);
        });
        modelBuilder.Entity<PieceJustificative>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<Contrat>().WithMany().HasForeignKey(x => x.ContratId);
        });
        modelBuilder.Entity<SignalementFraude>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.HasOne<Contrat>().WithMany().HasForeignKey(x => x.ContratId);
        });
        modelBuilder.Entity<Decision>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.Property(x => x.Motifs).HasColumnType("jsonb");
            e.Property(x => x.Citations).HasColumnType("jsonb");
            e.HasOne<Contrat>().WithMany().HasForeignKey(x => x.ContratId);
        });

        // Vue créée par SQL (migration VueEtDroits) : EF ne la crée pas, il la lit seulement.
        modelBuilder.Entity<LigneVue>(e =>
        {
            e.HasNoKey();
            e.ToView("vue_contrat_minimisee");
        });
    }
}
