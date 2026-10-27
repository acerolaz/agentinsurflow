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
        // relance aussi : le compteur lu en vient (un autre test peut en avoir laissé, selon l'ordre)
        foreach (var t in new[] { "relance", "tour_pilotage", "rapport_agent", "section_etat", "etat_dossier" })
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
    public async Task Relances_numerotees_comptees_dans_l_etat_et_bornees_au_gestionnaire()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        var migrateur = Connexions().Migrateur;
        await Lire(migrateur, "DELETE FROM relance WHERE numero_contrat = @p0", numero);
        foreach (var t in new[] { "tour_pilotage", "rapport_agent", "section_etat", "etat_dossier" })
            await Lire(migrateur, $"DELETE FROM {t} WHERE numero_contrat = @p0", numero);
        await depot.EnregistrerEtat(GestionnaireA, numero, new EtatEntrant("REVUE_HUMAINE", 1,
            [new("pieces", "{\"statut\":\"incomplet\",\"manquantes\":[\"releve_information\"]}")], [], []), ct);

        var avant = await depot.Situation(GestionnaireA, numero, ct);
        Assert.NotNull(avant);
        Assert.Equal(0, avant.Deja);
        Assert.Equal(["releve_information"], avant.Manquantes);
        Assert.Equal(1, await depot.Ajouter(GestionnaireA, numero, "<b>Bonjour</b>", ["releve_information"], ct));
        Assert.Equal(2, await depot.Ajouter(GestionnaireA, numero, "Encore", ["releve_information", "permis"], ct));

        Assert.Equal(2, (await depot.Situation(GestionnaireA, numero, ct))?.Deja);
        Assert.Null(await depot.Situation(GestionnaireB, numero, ct));
        Assert.Null(await depot.Situation(GestionnaireA, "AIF-INEXISTANT", ct));
        var lignes = await Lire(migrateur, "SELECT rang, texte, pieces::text, envoyee_par FROM relance WHERE numero_contrat = @p0 ORDER BY rang", numero);
        Assert.Equal(["1", "<b>Bonjour</b>", "[\"releve_information\"]", GestionnaireA], lignes[0].Select(o => o.ToString()));
        Assert.Equal(2L, (await Lire(migrateur, "SELECT nb_relances::bigint FROM etat_dossier WHERE numero_contrat = @p0", numero))[0][0]);
    }

    [Fact]
    public async Task Relances_comptees_sans_etat_dossier_et_rang_pris_rend_null()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        var migrateur = Connexions().Migrateur;
        await Lire(migrateur, "DELETE FROM relance WHERE numero_contrat = @p0", numero);
        foreach (var t in new[] { "tour_pilotage", "rapport_agent", "section_etat", "etat_dossier" })
            await Lire(migrateur, $"DELETE FROM {t} WHERE numero_contrat = @p0", numero);

        Assert.Equal(1, await depot.Ajouter(GestionnaireA, numero, "Avant l'état", ["permis"], ct));
        Assert.Equal(1, (await new DepotDossiersEf(db).LireEtat(GestionnaireA, numero, ct))?.NbRelances); // et non 0
        var statut = (string)(await Lire(migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0];
        var situation = await depot.Situation(GestionnaireA, numero, ct);
        Assert.Equal((1, statut is "ACCEPTE" or "REFUSE", 0), (situation!.Deja, situation.Decide, situation.Manquantes.Count)); // aucun rapport Pièces

        // envoi simultané : le rang 2 est déjà pris quand le compte en voit 1
        await Lire(migrateur, "DELETE FROM relance WHERE numero_contrat = @p0", numero);
        await Lire(migrateur, "INSERT INTO relance (numero_contrat, rang, texte, pieces, envoyee_le, envoyee_par) VALUES (@p0, 2, 'x', '[]'::jsonb, now(), @p1)", numero, GestionnaireA);
        Assert.Null(await depot.Ajouter(GestionnaireA, numero, "Course", ["permis"], ct));
    }

    [Fact]
    public async Task Sans_suite_ecrit_contrat_et_etat_jamais_sur_un_dossier_decide()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        var migrateur = Connexions().Migrateur;
        var origine = (string)(await Lire(migrateur, "SELECT statut FROM contrat WHERE numero_contrat = @p0", numero))[0][0];
        const string Statuts = "SELECT c.statut, e.statut_parcours FROM contrat c JOIN etat_dossier e USING (numero_contrat) WHERE c.numero_contrat = @p0";
        try
        {
            await Lire(migrateur, "UPDATE contrat SET statut = 'REVUE_HUMAINE' WHERE numero_contrat = @p0", numero);
            foreach (var t in new[] { "tour_pilotage", "rapport_agent", "section_etat", "etat_dossier" })
                await Lire(migrateur, $"DELETE FROM {t} WHERE numero_contrat = @p0", numero);
            await depot.EnregistrerEtat(GestionnaireA, numero, new EtatEntrant("REVUE_HUMAINE", 1, [], [], []), ct);

            Assert.False(await depot.ClasserSansSuite(GestionnaireB, numero, ct)); // BOLA : rien n'est écrit
            Assert.True(await depot.ClasserSansSuite(GestionnaireA, numero, ct));
            Assert.Equal(["SANS_SUITE", "SANS_SUITE"], (await Lire(migrateur, Statuts, numero))[0].Select(o => o.ToString()));
            Assert.True((await depot.Situation(GestionnaireA, numero, ct))?.Decide);
            Assert.False(await depot.ClasserSansSuite(GestionnaireA, numero, ct));

            await Lire(migrateur, "UPDATE contrat SET statut = 'ACCEPTE' WHERE numero_contrat = @p0", numero);
            Assert.False(await depot.ClasserSansSuite(GestionnaireA, numero, ct)); // décision entre-temps : la décision reste
            Assert.Equal("ACCEPTE", (await Lire(migrateur, Statuts, numero))[0][0]);
        }
        finally
        {
            await Lire(migrateur, "UPDATE contrat SET statut = @p1 WHERE numero_contrat = @p0", numero, origine);
        }
    }

    private static readonly VehiculeContrat VehiculeSeed1 = new("Marque", "Modele", "AA-001-AA", 5, "prive",
        "V1", "VIN00000000000001", new DateOnly(2019, 5, 1), "garage", "75011");

    [Fact]
    public async Task Contrat_genere_lu_apres_ACCEPTE_avec_le_compte_dossiers_et_borne_au_gestionnaire()
    {
        var (db, depot, numero) = await Preparer();
        await using var _ = db;
        var ct = TestContext.Current.CancellationToken;
        var migrateur = Connexions().Migrateur;
        foreach (var t in new[] { "tour_pilotage", "rapport_agent", "section_etat" })
            await Lire(migrateur, $"DELETE FROM {t} WHERE numero_contrat = @p0", numero);
        await Lire(migrateur, "UPDATE contrat SET statut = 'EN_ANALYSE' WHERE numero_contrat = @p0", numero);
        var lecteur = new DepotDossiersEf(db);

        Assert.Equal((null, true), await lecteur.LireContratGenere(GestionnaireA, numero, ct));

        await depot.EnregistrerBrouillon(GestionnaireA, numero, Fiche, Prime, ct);
        await depot.EnregistrerEtat(GestionnaireA, numero, new EtatEntrant("TERMINE", 1,
            [new("prime", """{"prime_ttc_annuelle":"512.40","prime_mensuelle":"42.70","version_formule":"f-1","explication":"x"}""")], [], []), ct);
        await depot.ChangerStatut(GestionnaireA, numero, new("ACCEPTE", "VALIDEE"), ct);
        var (contrat, existe) = await lecteur.LireContratGenere(GestionnaireA, numero, ct);

        Assert.True(existe);
        Assert.NotNull(contrat);
        Assert.Equal(("512.40", "42.70", "f-1", "v1", GestionnaireA), (contrat.PrimeTtcAnnuelle, contrat.PrimeMensuelle, contrat.VersionFormule, contrat.VersionBareme, contrat.ValidePar));
        Assert.Equal(["cit"], contrat.Citations);
        // Parties au contrat (seed du n° 1) : lues par vue_contrat_accepte, seulement après ACCEPTE
        Assert.Equal(new SouscripteurContrat("Nom1", "Prenom1", new DateOnly(1999, 3, 14), "1 rue Fictive", "75011",
            "PERMIS000001", new DateOnly(2018, 6, 1), "0600000001", "souscripteur1@exemple.invalid", "FR"), contrat.Souscripteur);
        Assert.Equal(VehiculeSeed1, contrat.Vehicule);
        Assert.Equal(0.9, contrat.CrmBonusMalus);
        // Formule tous_risques du n° 1 : garanties posées par la migration ContratComplet, franchise null = sans franchise
        Assert.Equal([new("assistance_0_km", null), new("bris_de_glace", 0m), new("dommages_tous_accidents", 450m),
            new("protection_juridique", 0m), new("responsabilite_civile", 300m), new GarantieContrat("vol_incendie_tempete", 300m)],
            contrat.Garanties);
        Assert.Equal((null, false), await lecteur.LireContratGenere(GestionnaireB, numero, ct));
    }

    [Fact]
    public async Task Fiche_souscripteur_lue_avec_le_compte_dossiers_et_bornee_au_gestionnaire()
    {
        var (db, _, numero) = await Preparer();
        await using var __ = db;
        var ct = TestContext.Current.CancellationToken;
        var lecteur = new DepotDossiersEf(db);

        // Seed du n° 1 (civilité posée par la migration FicheSouscripteur), quel que soit le statut du contrat
        Assert.Equal(new FicheSouscripteur("M.", "Nom1", "Prenom1", "1 rue Fictive", "75011", "0600000001",
            "souscripteur1@exemple.invalid", VehiculeSeed1),
            await lecteur.LireFiche(GestionnaireA, numero, ct));
        Assert.Null(await lecteur.LireFiche(GestionnaireB, numero, ct));
    }

    [Fact]
    public async Task Compte_dossiers_ne_lit_ni_souscripteur_ni_un_contrat_non_accepte_dans_la_vue_du_contrat()
    {
        var (db, _, numero) = await Preparer();
        await using var __ = db;
        var dossiers = Connexions().Dossiers;
        await Lire(Connexions().Migrateur, "UPDATE contrat SET statut = 'EN_ANALYSE' WHERE numero_contrat = @p0", numero);

        var refus = await Assert.ThrowsAsync<PostgresException>(() => Lire(dossiers, "SELECT nom FROM souscripteur LIMIT 1"));
        Assert.Equal("42501", refus.SqlState); // insufficient_privilege : la table reste fermée
        Assert.Empty(await Lire(dossiers, "SELECT nom FROM vue_contrat_accepte WHERE numero_contrat = @p0", numero));
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
