using AgentInsurFlow.UnderwritingAdmin.Domain;
using AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests;

/// <summary>
/// TI : base <c>dossiers_test</c> du PostgreSQL du compose (<c>docker compose up -d postgres</c>, variables PG_* du .env).
/// Une seule classe : ses tests passent l'un après l'autre sur la même base.
/// </summary>
[Collection("PostgresDossiers")] // même base que EcrituresPostgresTests : pas en parallèle
public sealed class DossiersPostgresTests
{
    private const string GestionnaireA = "11111111-1111-1111-1111-111111111111";
    private const string GestionnaireB = "22222222-2222-2222-2222-222222222222";

    static DossiersPostgresTests()
    {
        // La migration de seed lit ces variables : des valeurs fictives fixes, quelle que soit la machine.
        Environment.SetEnvironmentVariable("SEED_GESTIONNAIRE_A", GestionnaireA);
        Environment.SetEnvironmentVariable("SEED_GESTIONNAIRE_B", GestionnaireB);
    }

    private static string Env(string nom) => Environment.GetEnvironmentVariable(nom)
        ?? throw new InvalidOperationException($"{nom} manquant : lancer `docker compose up -d postgres` et exporter les PG_* du .env");

    private static ConnexionsDossiers Connexions() => new(
        Environment.GetEnvironmentVariable("PG_HOST") ?? "localhost",
        int.Parse(Environment.GetEnvironmentVariable("PG_PORT") ?? "5432", System.Globalization.CultureInfo.InvariantCulture),
        "_test", Env("PG_MIGRATEUR_PASSWORD"), Env("PG_DOSSIERS_PASSWORD"));

    private static Task Preparer() => MigrationsDossiers.AppliquerAsync(Connexions(), TimeSpan.FromSeconds(30), TestContext.Current.CancellationToken);

    private static async Task<List<object[]>> Lire(string chaine, string sql)
    {
        await using var cx = new NpgsqlConnection(chaine);
        await cx.OpenAsync(TestContext.Current.CancellationToken);
        await using var cmd = new NpgsqlCommand(sql, cx);
        await using var lecteur = await cmd.ExecuteReaderAsync(TestContext.Current.CancellationToken);
        var lignes = new List<object[]>();
        while (await lecteur.ReadAsync(TestContext.Current.CancellationToken))
        {
            var ligne = new object[lecteur.FieldCount];
            lecteur.GetValues(ligne);
            lignes.Add(ligne);
        }
        return lignes;
    }

    private static async Task<long> Compter(string table) =>
        (long)(await Lire(Connexions().Migrateur, $"SELECT count(*) FROM {table}"))[0][0];

    [Fact]
    public async Task Migrations_s_appliquent_sur_base_vierge_puis_rejouables()
    {
        // Base vierge : on repart d'un schéma public neuf (le propriétaire de la base peut le recréer).
        await Lire(Connexions().Migrateur, "DROP SCHEMA public CASCADE");
        await Lire(Connexions().Migrateur, "CREATE SCHEMA public");

        await Preparer();
        await Preparer();

        await using var db = DossiersDbContextFactory.Creer(Connexions().Migrateur);
        Assert.Equal(5, (await db.Database.GetAppliedMigrationsAsync(TestContext.Current.CancellationToken)).Count());
        Assert.Empty(await db.Database.GetPendingMigrationsAsync(TestContext.Current.CancellationToken));
        var tables = await Lire(Connexions().Migrateur,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' AND table_name <> '__EFMigrationsHistory'");
        Assert.Equal(12L, tables[0][0]);
    }

    [Fact]
    public async Task Vue_n_expose_aucune_donnee_personnelle()
    {
        await Preparer();

        var colonnes = await Lire(Connexions().Migrateur,
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'vue_contrat_minimisee'");

        Assert.Equal(
            ["anciennete_permis_ans", "anciennete_permis_mois", "crm_bonus_malus", "date_effet", "departement", "formule",
                "gestionnaire_id", "mis_a_jour", "nb_sinistres", "nb_sinistres_responsables_trois_ans", "nb_sinistres_trois_ans",
                "numero_contrat", "puissance_fiscale_cv", "releve_present", "resiliations", "suspensions", "tranche_age", "type_usage"],
            colonnes.Select(c => (string)c[0]).Order(StringComparer.Ordinal));
    }

    private static async Task<List<object[]>> LireDansTransactionAnnulee(string inserts, string sql)
    {
        await using var cx = new NpgsqlConnection(Connexions().Migrateur);
        await cx.OpenAsync(TestContext.Current.CancellationToken);
        await using var tx = await cx.BeginTransactionAsync(TestContext.Current.CancellationToken);
        await using (var ecriture = new NpgsqlCommand(inserts, cx, tx))
            await ecriture.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
        await using var cmd = new NpgsqlCommand(sql, cx, tx);
        await using var lecteur = await cmd.ExecuteReaderAsync(TestContext.Current.CancellationToken);
        var lignes = new List<object[]>();
        while (await lecteur.ReadAsync(TestContext.Current.CancellationToken))
        {
            var ligne = new object[lecteur.FieldCount];
            lecteur.GetValues(ligne);
            lignes.Add(ligne);
        }
        return lignes; // la transaction n'est pas validée : tout est annulé à la fermeture
    }

    private const string ContratSansVehicule = """
        INSERT INTO souscripteur (id, nom, prenom, date_naissance, adresse, email, telephone, situation_familiale, permis_numero, permis_date_obtention, permis_pays, code_postal)
        VALUES ('aaaaaaaa-0000-0000-0000-000000000001', 'N', 'P', '1990-01-01', 'a', 'e@exemple.invalid', '0', 'celibataire', 'PX', '2020-01-01', 'FR', '75001');
        INSERT INTO contrat (id, numero_contrat, souscripteur_id, gestionnaire_id, date_effet, statut, formule, mis_a_jour)
        VALUES ('aaaaaaaa-0000-0000-0000-000000000002', 'AIF-TEST-1', 'aaaaaaaa-0000-0000-0000-000000000001', 'g', '2026-01-01', 'actif', 'tous_risques', '2026-10-01T08:00:00Z');
        INSERT INTO releve_information (id, contrat_id, crm_bonus_malus, nb_suspensions_permis, nb_resiliations)
        VALUES ('aaaaaaaa-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000002', 1, 0, 0);
        """;

    [Fact]
    public async Task Vue_calcule_les_faits_du_calcul_a_la_date_d_effet()
    {
        await Preparer();
        await Lire(Connexions().Migrateur, SeedDossiers.Sql(GestionnaireA, GestionnaireB));

        var lignes = await Lire(Connexions().Migrateur,
            "SELECT numero_contrat, anciennete_permis_mois, puissance_fiscale_cv, type_usage, nb_sinistres_trois_ans, nb_sinistres_responsables_trois_ans, date_effet " +
            "FROM vue_contrat_minimisee WHERE numero_contrat IN ('AIF-2026-000001', 'AIF-2026-000004')");

        var un = lignes.Single(l => (string)l[0] == "AIF-2026-000001");
        Assert.Equal([91, 5, "prive", 0, 0], [un[1], un[2], un[3], un[4], un[5]]);
        Assert.Equal(new DateOnly(2026, 1, 1), un[6]);
        var quatre = lignes.Single(l => (string)l[0] == "AIF-2026-000004");
        Assert.Equal([70, 2, 2], [quatre[1], quatre[4], quatre[5]]);
    }

    [Fact]
    public async Task Vue_sans_vehicule_rend_puissance_et_usage_nuls()
    {
        await Preparer();

        var lignes = await LireDansTransactionAnnulee(ContratSansVehicule,
            "SELECT puissance_fiscale_cv, type_usage FROM vue_contrat_minimisee WHERE numero_contrat = 'AIF-TEST-1'");

        Assert.Equal([DBNull.Value, DBNull.Value], lignes.Single());
    }

    [Fact]
    public async Task Vue_sans_releve_rend_releve_present_faux_et_le_seed_vrai()
    {
        await Preparer();
        await Lire(Connexions().Migrateur, SeedDossiers.Sql(GestionnaireA, GestionnaireB));
        var seed = await Lire(Connexions().Migrateur,
            "SELECT releve_present FROM vue_contrat_minimisee WHERE numero_contrat = 'AIF-2026-000001'");
        Assert.Equal(true, seed.Single()[0]);

        var sansReleve = ContratSansVehicule[..ContratSansVehicule.IndexOf("INSERT INTO releve_information", StringComparison.Ordinal)];
        var lignes = await LireDansTransactionAnnulee(sansReleve,
            "SELECT releve_present FROM vue_contrat_minimisee WHERE numero_contrat = 'AIF-TEST-1'");

        Assert.Equal(false, lignes.Single()[0]);
    }

    [Fact]
    public async Task Vue_ne_compte_pas_un_sinistre_hors_des_trois_ans()
    {
        await Preparer();
        const string sinistres = """
            INSERT INTO sinistre (id, releve_information_id, date_sinistre, nature, taux_responsabilite) VALUES
            ('bbbbbbbb-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000003', '2022-12-01', 'materiel', 100),
            ('bbbbbbbb-0000-0000-0000-000000000002', 'aaaaaaaa-0000-0000-0000-000000000003', '2026-01-01', 'materiel', 100),
            ('bbbbbbbb-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000003', '2025-06-01', 'materiel', 0);
            """;

        var lignes = await LireDansTransactionAnnulee(ContratSansVehicule + sinistres,
            "SELECT nb_sinistres_trois_ans, nb_sinistres_responsables_trois_ans FROM vue_contrat_minimisee WHERE numero_contrat = 'AIF-TEST-1'");

        Assert.Equal([1, 0], lignes.Single());
    }

    [Theory]
    [InlineData("souscripteur")]
    [InlineData("contrat")] // seules id, numero_contrat, gestionnaire_id sont lisibles (colonnes), jamais la table entière
    public async Task Compte_dossiers_ne_lit_pas_les_tables(string table)
    {
        await Preparer();

        var erreur = await Assert.ThrowsAsync<PostgresException>(() => Lire(Connexions().Dossiers, $"SELECT * FROM {table}"));

        Assert.Equal(PostgresErrorCodes.InsufficientPrivilege, erreur.SqlState);
    }

    [Fact]
    public async Task Compte_dossiers_lit_la_vue_mais_n_ecrit_pas()
    {
        await Preparer();

        Assert.NotEmpty(await Lire(Connexions().Dossiers, "SELECT * FROM vue_contrat_minimisee"));
        // Aucun droit d'écriture, sur la vue comme sur les tables : SELECT seulement.
        var droits = await Lire(Connexions().Migrateur,
            "SELECT has_table_privilege('dossiers', 'vue_contrat_minimisee', 'INSERT, UPDATE, DELETE'), has_table_privilege('dossiers', 'souscripteur', 'SELECT')");
        Assert.Equal([false, false], [droits[0][0], droits[0][1]]);
    }

    [Fact]
    public async Task Seed_idempotent()
    {
        await Preparer();
        // Remet le seed complet : les TI d'écriture ont pu supprimer une prime ou une décision.
        await Lire(Connexions().Migrateur, SeedDossiers.Sql(GestionnaireA, GestionnaireB));
        var avant = new[] { await Compter("contrat"), await Compter("sinistre"), await Compter("prime"), await Compter("souscripteur") };

        // Rejoué deux fois : aucun doublon, aucune erreur.
        await Lire(Connexions().Migrateur, SeedDossiers.Sql(GestionnaireA, GestionnaireB));
        await Lire(Connexions().Migrateur, SeedDossiers.Sql(GestionnaireA, GestionnaireB));

        var apres = new[] { await Compter("contrat"), await Compter("sinistre"), await Compter("prime"), await Compter("souscripteur") };
        Assert.Equal(avant, apres);
        Assert.Equal(6L, avant[0]);
    }

    [Fact]
    public void Seed_sans_variables_ne_fait_rien() =>
        Assert.Equal("SELECT 1", SeedDossiers.Sql(null, GestionnaireB));

    [Fact]
    public void Seed_oid_invalide_nomme_la_variable()
    {
        var erreur = Assert.Throws<InvalidOperationException>(() => SeedDossiers.Sql("pas-un-guid", GestionnaireB));
        Assert.Contains("SEED_GESTIONNAIRE_A", erreur.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Depot_ne_rend_que_les_contrats_du_gestionnaire_et_suit_les_regles_du_domaine()
    {
        await Preparer();
        await using var db = DossiersDbContextFactory.Creer(Connexions().Dossiers);
        var depot = new DepotDossiersEf(db);
        var ct = TestContext.Current.CancellationToken;

        var deA = await depot.Lister(GestionnaireA, 100, 0, ct);
        var deB = await depot.Lister(GestionnaireB, 100, 0, ct);

        Assert.Equal(3, deA.Count);
        Assert.Equal(3, deB.Count);
        Assert.Empty(deA.Select(v => v.NumeroContrat).Intersect(deB.Select(v => v.NumeroContrat)));
        Assert.Single(await depot.Lister(GestionnaireA, 1, 0, ct));
        Assert.Null(await depot.Trouver(GestionnaireA, deB[0].NumeroContrat, ct));
        Assert.Null(await depot.Trouver(GestionnaireA, "AIF-INEXISTANT", ct));

        // La vue SQL et les règles du Domain donnent les mêmes tranches et départements.
        var aujourdhui = DateOnly.FromDateTime(DateTime.UtcNow);
        foreach (var l in await Lire(Connexions().Migrateur,
                     "SELECT c.numero_contrat, s.date_naissance, s.permis_date_obtention, s.code_postal FROM contrat c JOIN souscripteur s ON s.id = c.souscripteur_id"))
        {
            var vue = await depot.Trouver(GestionnaireA, (string)l[0], ct) ?? await depot.Trouver(GestionnaireB, (string)l[0], ct);
            Assert.NotNull(vue);
            Assert.Equal(TrancheAge.Depuis(Annees((DateOnly)l[1], aujourdhui)), vue.TrancheAge);
            Assert.Equal(Annees((DateOnly)l[2], aujourdhui), vue.AnciennetePermisAns);
            Assert.Equal(Departement.Depuis((string)l[3]), vue.Departement);
        }
    }

    private static int Annees(DateOnly depuis, DateOnly jusqua) =>
        jusqua.Year - depuis.Year - (jusqua < depuis.AddYears(jusqua.Year - depuis.Year) ? 1 : 0);

    [Fact]
    public async Task Migrations_au_demarrage_abandonnent_apres_l_attente_si_postgres_est_injoignable()
    {
        var injoignable = Connexions() with { Hote = "localhost", Port = 1 };

        await Assert.ThrowsAsync<TimeoutException>(() =>
            MigrationsDossiers.AppliquerAsync(injoignable, TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken));
    }

    [Fact]
    public void Migrateur_sans_mot_de_passe_est_refuse() =>
        Assert.Throws<InvalidOperationException>(() => (Connexions() with { MotDePasseMigrateur = null }).Migrateur);
}
