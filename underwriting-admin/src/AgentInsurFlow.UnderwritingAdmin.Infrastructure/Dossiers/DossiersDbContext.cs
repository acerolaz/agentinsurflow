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
            e.ToTable(t => t.HasCheckConstraint("ck_contrat_observations_longueur", "char_length(observations) <= 2000"));
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

        // Mémoire long terme du dossier (D100) : les écritures passent par du SQL en upsert / insertion idempotente.
        // Clés primaires composites = la contrainte d'unicité métier ; clés étrangères de l'ER : contrat ← état ← le reste.
        modelBuilder.Entity<EtatDossier>(e =>
        {
            e.HasKey(x => x.NumeroContrat);
            e.HasOne<Contrat>().WithOne().HasForeignKey<EtatDossier>(x => x.NumeroContrat).HasPrincipalKey<Contrat>(c => c.NumeroContrat);
        });
        modelBuilder.Entity<SectionEtat>(e =>
        {
            e.HasKey(x => new { x.NumeroContrat, x.Section, x.Tentative });
            e.Property(x => x.Contenu).HasColumnType("jsonb");
            e.HasOne<EtatDossier>().WithMany().HasForeignKey(x => x.NumeroContrat);
        });
        modelBuilder.Entity<RapportAgent>(e =>
        {
            e.HasKey(x => new { x.NumeroContrat, x.Agent, x.Tentative, x.TraceId });
            e.Property(x => x.Rapport).HasColumnType("jsonb");
            e.Property(x => x.CreeLe).HasDefaultValueSql("now()");
            e.HasOne<EtatDossier>().WithMany().HasForeignKey(x => x.NumeroContrat);
        });
        modelBuilder.Entity<TourPilotage>(e =>
        {
            e.HasKey(x => new { x.NumeroContrat, x.Tentative, x.Tour });
            e.HasOne<EtatDossier>().WithMany().HasForeignKey(x => x.NumeroContrat);
        });
        // Relances de pièces manquantes (#130) : le rang fait la clé, trois au plus (règle du Domain).
        modelBuilder.Entity<Relance>(e =>
        {
            e.HasKey(x => new { x.NumeroContrat, x.Rang });
            e.Property(x => x.Pieces).HasColumnType("jsonb");
            e.Property(x => x.EnvoyeeLe).HasDefaultValueSql("now()");
            e.HasOne<Contrat>().WithMany().HasForeignKey(x => x.NumeroContrat).HasPrincipalKey(c => c.NumeroContrat);
        });

        // Vue créée par SQL (migration VueEtDroits) : EF ne la crée pas, il la lit seulement.
        modelBuilder.Entity<LigneVue>(e =>
        {
            e.HasNoKey();
            e.ToView("vue_contrat_minimisee");
        });
        modelBuilder.Entity<PartiesContratAccepte>(e =>
        {
            e.HasNoKey();
            e.ToView("vue_contrat_accepte");
        });
        modelBuilder.Entity<LigneFicheSouscripteur>(e =>
        {
            e.HasNoKey();
            e.ToView("vue_fiche_souscripteur");
        });
    }
}
