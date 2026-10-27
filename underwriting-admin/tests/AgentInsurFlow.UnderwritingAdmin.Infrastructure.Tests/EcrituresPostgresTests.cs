using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;
using Npgsql;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests;

/// <summary>TI : écritures du compte <c>dossiers</c> sur <c>dossiers_test</c> (PostgreSQL du compose).</summary>
[Collection("PostgresDossiers")] // même base que DossiersPostgresTests : pas en parallèle
public sealed class EcrituresPostgresTests
{
    private const string GestionnaireA = "11111111-1111-1111-1111-111111111111";
    private const string GestionnaireB = "22222222-2222-2222-2222-222222222222";

    static EcrituresPostgresTests()
    {
        Environment.SetEnvironmentVariable("SEED_GESTIONNAIRE_A", GestionnaireA);
        Environment.SetEnvironmentVariable("SEED_GESTIONNAIRE_B", GestionnaireB);
    }

    private static string Env(string nom) => Environment.GetEnvironmentVariable(nom)
        ?? throw new InvalidOperationException($"{nom} manquant : lancer `docker compose up -d postgres` et exporter les PG_* du .env");

    private static ConnexionsDossiers Connexions() => new(
        Environment.GetEnvironmentVariable("PG_HOST") ?? "localhost",
        int.Parse(Environment.GetEnvironmentVariable("PG_PORT") ?? "5432", System.Globalization.CultureInfo.InvariantCulture),
        "_test", Env("PG_MIGRATEUR_PASSWORD"), Env("PG_DOSSIERS_PASSWORD"));

    private static readonly FicheBrouillon Fiche = new("ACCEPTE", "tous_risques", 0.8m, "v1", ["R1", "R2"], ["motif"], ["cit"]);
    private static readonly PrimeBrouillon Prime = new(512.40m, "mensuelle", new DateOnly(2026, 11, 1));

    private static async Task<List<object[]>> Lire(string chaine, string sql, params object[] parametres)
    {
        await using var cx = new NpgsqlConnection(chaine);
        await cx.OpenAsync(TestContext.Current.CancellationToken);
        await using var cmd = new NpgsqlCommand(sql, cx);
        foreach (var (p, i) in parametres.Select((p, i) => (p, i))) cmd.Parameters.AddWithValue($"p{i}", p);
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

    /// <summary>Base prête, dépôt branché sur le compte <c>dossiers</c> et un contrat de A repris à zéro (sans décision ni prime).</summary>
    private static async Task<(DossiersDbContext Db, DepotEcrituresEf Depot, string Numero)> Preparer()
    {
        var ct = TestContext.Current.CancellationToken;
        await MigrationsDossiers.AppliquerAsync(Connexions(), TimeSpan.FromSeconds(30), ct);
        var migrateur = Connexions().Migrateur;
        var numero = (string)(await Lire(migrateur, "SELECT numero_contrat FROM contrat WHERE gestionnaire_id = @p0 ORDER BY numero_contrat LIMIT 1", GestionnaireA))[0][0];
        await Lire(migrateur, "DELETE FROM decision WHERE contrat_id = (SELECT id FROM contrat WHERE numero_contrat = @p0)", numero);
        await Lire(migrateur, "DELETE FROM prime WHERE contrat_id = (SELECT id FROM contrat WHERE numero_contrat = @p0)", numero);
        var db = DossiersDbContextFactory.Creer(Connexions().Dossiers);
        return (db, new DepotEcrituresEf(db, TimeProvider.System), numero);
    }

    private static Task<List<object[]>> Decisions(string numero) => Lire(Connexions().Migrateur,
        "SELECT d.etat_validation, d.decision_rendue, d.auteur, d.regle_id, d.motifs::text FROM decision d JOIN contrat c ON c.id = d.contrat_id WHERE c.numero_contrat = @p0", numero);

    private static Task<List<object[]>> Primes(string numero) => Lire(Connexions().Migrateur,
        "SELECT p.prime_ttc, p.periodicite, p.etat_validation FROM prime p JOIN contrat c ON c.id = p.contrat_id WHERE c.numero_contrat = @p0", numero);

    [Fact]
    public async Task Brouillon_rejoue_deux_fois_une_seule_decision_et_une_seule_prime()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        var avant = (string)(await Lire(Connexions().Migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0];

        Assert.True(await depot.EnregistrerBrouillon(GestionnaireA, numero, Fiche, Prime, ct));
        Assert.True(await depot.EnregistrerBrouillon(GestionnaireA, numero, Fiche with { Decision = "REFUSE" }, Prime with { PrimeTtc = 600m }, ct));

        var d = Assert.Single(await Decisions(numero));
        Assert.Equal(["brouillon", "REFUSE", "agent", "R1,R2", "[\"motif\"]"], d.Select(o => o.ToString()));
        var p = Assert.Single(await Primes(numero));
        Assert.Equal((600m, "mensuelle", "brouillon"), ((decimal)p[0], (string)p[1], (string)p[2]));
        Assert.Equal(avant, (string)(await Lire(Connexions().Migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0]);
    }

    [Fact]
    public async Task Observations_ecrasees_lues_par_la_vue_et_bornees_au_gestionnaire()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;

        Assert.NotNull(await depot.StatutContrat(GestionnaireA, numero, ct));
        Assert.Null(await depot.StatutContrat(GestionnaireB, numero, ct));
        Assert.True(await depot.EnregistrerObservations(GestionnaireA, numero, "premier", ct));
        Assert.True(await depot.EnregistrerObservations(GestionnaireA, numero, "second", ct));
        Assert.False(await depot.EnregistrerObservations(GestionnaireB, numero, "pirate", ct));

        var vue = await new DepotDossiersEf(db).Trouver(GestionnaireA, numero, ct);
        Assert.Equal("second", vue!.Observations);
        await Assert.ThrowsAsync<PostgresException>(() => depot.EnregistrerObservations(GestionnaireA, numero, new string('a', 2001), ct));
    }

    [Fact]
    public async Task Etat_rejoue_deux_fois_une_ligne_par_table_et_borne_au_gestionnaire()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        var migrateur = Connexions().Migrateur;
        foreach (var t in new[] { "tour_pilotage", "rapport_agent", "section_etat", "etat_dossier" })
            await Lire(migrateur, $"DELETE FROM {t} WHERE numero_contrat = @p0", numero);
        var etat = new EtatEntrant("EN_COURS", 2, [new("risque", "{\"score\":0.4}")],
            [new("risque", "{\"resume\":\"ok\"}", "llm", null, "v1", "t-1")], [new(1, "evaluer_risque", "pieces_ok", "llm")]);

        Assert.True(await depot.EnregistrerEtat(GestionnaireA, numero, etat, ct));
        Assert.True(await depot.EnregistrerEtat(GestionnaireA, numero, etat with { StatutParcours = "TERMINE", Sections = [new("risque", "{\"score\":0.5}")] }, ct));
        Assert.False(await depot.EnregistrerEtat(GestionnaireB, numero, etat, ct));
        // Écriture périmée : une tentative plus ancienne ne remplace pas l'état (tentative 2 reste).
        Assert.True(await depot.EnregistrerEtat(GestionnaireA, numero, etat with { StatutParcours = "PERIME", Tentative = 1, Sections = [], Rapports = [], Tours = [] }, ct));

        var e = Assert.Single(await Lire(migrateur, "SELECT statut_parcours, tentative, version_schema, nb_relances FROM etat_dossier WHERE numero_contrat = @p0", numero));
        Assert.Equal(["TERMINE", "2", "1", "0"], e.Select(o => o.ToString()));
        var sec = Assert.Single(await Lire(migrateur, "SELECT contenu::text FROM section_etat WHERE numero_contrat = @p0", numero));
        Assert.Equal("{\"score\": 0.5}", sec[0]);
        Assert.Single(await Lire(migrateur, "SELECT 1 FROM rapport_agent WHERE numero_contrat = @p0", numero));
        Assert.Single(await Lire(migrateur, "SELECT 1 FROM tour_pilotage WHERE numero_contrat = @p0", numero));
        Assert.Empty(await Lire(migrateur, "SELECT 1 FROM etat_dossier WHERE numero_contrat = @p0 AND statut_parcours = 'EN_COURS'", numero));
    }

    [Fact]
    public async Task Etat_lu_tentative_courante_rapports_dans_l_ordre_et_borne_au_gestionnaire()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        var migrateur = Connexions().Migrateur;
        foreach (var t in new[] { "tour_pilotage", "rapport_agent", "section_etat", "etat_dossier" })
            await Lire(migrateur, $"DELETE FROM {t} WHERE numero_contrat = @p0", numero);
        var lecteur = new DepotDossiersEf(db);

        var vide = await lecteur.LireEtat(GestionnaireA, numero, ct);
        Assert.NotNull(vide);
        Assert.Equal((null, 0, 0), (vide.StatutParcours, vide.Tentative, vide.NbRelances));
        Assert.Empty(vide.Rapports);
        Assert.Empty(vide.Sections);
        await depot.EnregistrerEtat(GestionnaireA, numero, new EtatEntrant("EN_COURS", 1, [new("pieces", "{\"statut\":\"ancien\"}")],
            [new("pieces", "{}", "llm", null, "v1", "t-ancien")], []), ct);
        await depot.EnregistrerEtat(GestionnaireA, numero, new EtatEntrant("EN_COURS", 2, [new("pieces", "{\"statut\":\"complet\"}")],
            [new("pieces", "{}", "llm", null, "v1", "t-2")], []), ct);
        await depot.EnregistrerEtat(GestionnaireA, numero, new EtatEntrant("EN_COURS", 2, [new("risque", "{\"score\":1}")],
            [new("pieces", "{}", "llm", null, "v1", "t-2"), new("analyste", "{}", "repli", "llm_ko", "v1", "t-2")], []), ct);

        var etat = await lecteur.LireEtat(GestionnaireA, numero, ct);

        Assert.NotNull(etat);
        Assert.Equal(("EN_COURS", 2), (etat.StatutParcours, etat.Tentative));
        Assert.Equal(["pieces", "analyste"], etat.Rapports.Select(r => r.Agent));
        Assert.True(etat.Rapports[0].CreeLe <= etat.Rapports[1].CreeLe);
        Assert.Equal(["pieces", "risque"], etat.Sections.Keys.Order());
        Assert.Contains("complet", etat.Sections["pieces"], StringComparison.Ordinal);
        Assert.Null(await lecteur.LireEtat(GestionnaireB, numero, ct));
        Assert.Null(await lecteur.LireEtat(GestionnaireA, "AIF-INEXISTANT", ct));
    }

    [Fact]
    public async Task Brouillon_contrat_d_un_autre_gestionnaire_rend_false_et_n_ecrit_rien()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;

        Assert.False(await depot.EnregistrerBrouillon(GestionnaireB, numero, Fiche, Prime, TestContext.Current.CancellationToken));
        Assert.False(await depot.EnregistrerBrouillon(GestionnaireA, "AIF-INEXISTANT", Fiche, Prime, TestContext.Current.CancellationToken));

        Assert.Empty(await Decisions(numero));
        Assert.Empty(await Primes(numero));
    }

    [Fact]
    public async Task Statut_valide_passe_la_decision_a_VALIDEE_avec_auteur_oid()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        await depot.EnregistrerBrouillon(GestionnaireA, numero, Fiche, Prime, ct);

        Assert.Equal(new ResultatEcriture(true, null), await depot.ChangerStatut(GestionnaireA, numero, new("ACCEPTE", "VALIDEE"), ct));

        var d = Assert.Single(await Decisions(numero));
        Assert.Equal(["VALIDEE", "ACCEPTE", GestionnaireA], d.Take(3).Select(o => o.ToString()));
        Assert.Equal("ACCEPTE", (string)(await Lire(Connexions().Migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0]);
    }

    [Fact]
    public async Task Statut_CORRIGEE_remplace_la_decision_rendue()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        await depot.EnregistrerBrouillon(GestionnaireA, numero, Fiche, Prime, ct); // brouillon ACCEPTE

        Assert.Equal(new ResultatEcriture(true, null), await depot.ChangerStatut(GestionnaireA, numero, new("REFUSE", "CORRIGEE"), ct));

        var d = Assert.Single(await Decisions(numero));
        Assert.Equal(["CORRIGEE", "REFUSE", GestionnaireA], d.Take(3).Select(o => o.ToString()));
    }

    [Fact]
    public async Task Statut_avec_validation_sans_brouillon_refuse_DECISION_ABSENTE_et_ne_change_rien()
    {
        var (db, depot, numero) = await Preparer(); // contrat sans décision
        await using var _ = db;
        var avant = (string)(await Lire(Connexions().Migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0];

        var r = await depot.ChangerStatut(GestionnaireA, numero, new("ACCEPTE", "VALIDEE"), TestContext.Current.CancellationToken);

        Assert.Equal(new ResultatEcriture(false, "DECISION_ABSENTE"), r);
        Assert.Equal(avant, (string)(await Lire(Connexions().Migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0]);
        Assert.Empty(await Decisions(numero));
    }

    [Fact]
    public async Task Statut_autre_gestionnaire_rend_false_et_ne_change_rien()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var avant = (string)(await Lire(Connexions().Migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0];

        Assert.Equal(new ResultatEcriture(false, null), await depot.ChangerStatut(GestionnaireB, numero, new("REFUSE", "VALIDEE"), TestContext.Current.CancellationToken));

        Assert.Equal(avant, (string)(await Lire(Connexions().Migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0]);
    }

    [Fact]
    public async Task Compte_dossiers_ne_peut_pas_modifier_le_souscripteur()
    {
        var (db, _, _) = await Preparer();
        await using var _ = db;

        var erreur = await Assert.ThrowsAsync<PostgresException>(() =>
            Lire(Connexions().Dossiers, "UPDATE souscripteur SET nom = 'x'"));

        Assert.Equal(PostgresErrorCodes.InsufficientPrivilege, erreur.SqlState);
    }

    [Fact]
    public async Task Compte_dossiers_ne_peut_modifier_du_contrat_que_statut_et_mis_a_jour()
    {
        var (db, _, _) = await Preparer();
        await using var _ = db;

        var erreur = await Assert.ThrowsAsync<PostgresException>(() =>
            Lire(Connexions().Dossiers, "UPDATE contrat SET gestionnaire_id = 'x'"));

        Assert.Equal(PostgresErrorCodes.InsufficientPrivilege, erreur.SqlState);
    }
}
