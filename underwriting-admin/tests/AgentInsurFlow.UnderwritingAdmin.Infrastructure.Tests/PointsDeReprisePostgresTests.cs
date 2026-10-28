using AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;
using AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise;
using Npgsql;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests;

/// <summary>
/// TI : schéma <c>points_reprise</c> de la base <c>dossiers_test</c> du PostgreSQL du compose
/// (<c>docker compose up -d postgres</c>, variables PG_* du .env, dont PG_POINTS_REPRISE_PASSWORD).
/// Chaque test travaille sur son propre <c>thread_id</c> : pas d'interférence entre eux.
/// </summary>
[Collection("PostgresDossiers")] // même base que DossiersPostgresTests, qui recrée le schéma public
public sealed class PointsDeReprisePostgresTests
{
    private const string Ns = "";

    static PointsDeReprisePostgresTests()
    {
        // La migration de seed des dossiers lit ces variables : des valeurs fictives fixes.
        Environment.SetEnvironmentVariable("SEED_GESTIONNAIRE_A", "11111111-1111-1111-1111-111111111111");
        Environment.SetEnvironmentVariable("SEED_GESTIONNAIRE_B", "22222222-2222-2222-2222-222222222222");
    }

    private static string Env(string nom) => Environment.GetEnvironmentVariable(nom)
        ?? throw new InvalidOperationException($"{nom} manquant : lancer `docker compose up -d postgres` et exporter les PG_* du .env");

    private static string Hote => Environment.GetEnvironmentVariable("PG_HOST") ?? "localhost";

    private static int Port => int.Parse(Environment.GetEnvironmentVariable("PG_PORT") ?? "5432", System.Globalization.CultureInfo.InvariantCulture);

    private static ConnexionsPointsDeReprise Connexions() =>
        new(Hote, Port, "_test", Env("PG_MIGRATEUR_PASSWORD"), Env("PG_POINTS_REPRISE_PASSWORD"));

    private static async Task<DepotPointsDeRepriseEf> Preparer()
    {
        await MigrationsPointsDeReprise.AppliquerAsync(Connexions(), TimeSpan.FromSeconds(30), TestContext.Current.CancellationToken);
        return new DepotPointsDeRepriseEf(Connexions());
    }

    private static string UnFil() => "AIF-" + Guid.NewGuid().ToString("N");

    private static PointDeReprise UnPoint(string fil, string id, string? parent = null, IReadOnlyList<EcritureEnAttente>? ecritures = null) =>
        new(fil, Ns, id, parent, "msgpack", [0x00, 0xFF, 0x10, (byte)id[^1]], "json", [0x7B, 0x7D, 0x00], ecritures ?? []);

    private static EcritureEnAttente UneEcriture(string tache, int idx, byte[] valeur, string canal = "canal") =>
        new(tache, idx, canal, "msgpack", valeur, "chemin");

    [Fact]
    public async Task Lecture_apres_ecriture_rend_les_memes_octets()
    {
        var ct = TestContext.Current.CancellationToken;
        var depot = await Preparer();
        var fil = UnFil();
        await depot.EcrireAsync(UnPoint(fil, "1ef-0001"), ct);
        // task_id et task_path viennent des arguments de la tâche, pas de chaque écriture
        await depot.EcrireEcrituresAsync(fil, Ns, "1ef-0001", "t2", "chemin", [UneEcriture("t2", 0, [2, 0, 255])], ct);
        await depot.EcrireEcrituresAsync(fil, Ns, "1ef-0001", "t1", "chemin", [UneEcriture("t1", 1, [1, 1]), UneEcriture("t1", 0, [1, 0])], ct);

        var lu = await depot.LireAsync(fil, Ns, "1ef-0001", ct);

        Assert.NotNull(lu);
        Assert.Equal(UnPoint(fil, "1ef-0001").Checkpoint, lu.Checkpoint);
        Assert.Equal(UnPoint(fil, "1ef-0001").Metadata, lu.Metadata);
        Assert.Equal("msgpack", lu.Type);
        Assert.Equal("json", lu.TypeMetadata);
        Assert.Null(lu.ParentId);
        // triées par (task_id, idx)
        Assert.Equal([("t1", 0), ("t1", 1), ("t2", 0)], lu.Ecritures.Select(e => (e.TaskId, e.Idx)));
        Assert.Equal([2, 0, 255], lu.Ecritures[2].Valeur);
        Assert.Equal("chemin", lu.Ecritures[0].TaskPath);
        Assert.Null(await depot.LireAsync(fil, Ns, "inconnu", ct));
        Assert.Null(await depot.LireAsync(UnFil(), Ns, null, ct));
    }

    [Fact]
    public async Task Lecture_du_dernier_point_sans_id()
    {
        var ct = TestContext.Current.CancellationToken;
        var depot = await Preparer();
        var fil = UnFil();
        await depot.EcrireAsync(UnPoint(fil, "1ef-0002", "1ef-0001"), ct);
        await depot.EcrireAsync(UnPoint(fil, "1ef-0001"), ct);
        await depot.EcrireAsync(UnPoint(fil, "1ef-0003", "1ef-0002"), ct);

        var dernier = await depot.LireAsync(fil, Ns, null, ct);

        Assert.Equal("1ef-0003", dernier?.CheckpointId);
        Assert.Equal("1ef-0002", dernier?.ParentId);
    }

    [Fact]
    public async Task Reecriture_d_un_point_remplace_le_contenu()
    {
        var ct = TestContext.Current.CancellationToken;
        var depot = await Preparer();
        var fil = UnFil();
        await depot.EcrireAsync(UnPoint(fil, "1ef-0001"), ct);
        await depot.EcrireAsync(UnPoint(fil, "1ef-0001") with { Checkpoint = [9, 9], ParentId = "1ef-0000" }, ct);

        var lu = await depot.LireAsync(fil, Ns, "1ef-0001", ct);

        Assert.Equal([9, 9], lu?.Checkpoint);
        Assert.Equal("1ef-0000", lu?.ParentId);
        Assert.Single(await depot.ListerAsync(fil, null, null, null, ct));
    }

    [Fact]
    public async Task Liste_decroissante_avec_avant_et_limite()
    {
        var ct = TestContext.Current.CancellationToken;
        var depot = await Preparer();
        var fil = UnFil();
        foreach (var id in new[] { "1ef-0002", "1ef-0004", "1ef-0001", "1ef-0003" })
        {
            await depot.EcrireAsync(UnPoint(fil, id), ct);
        }
        await depot.EcrireEcrituresAsync(fil, Ns, "1ef-0004", "t", "p", [UneEcriture("t", 0, [4])], ct);
        await depot.EcrireAsync(UnPoint(fil, "1ef-0009") with { Ns = "sous|graphe" }, ct);

        var tous = await depot.ListerAsync(fil, null, null, null, ct);
        var racine = await depot.ListerAsync(fil, Ns, null, null, ct);
        var avant = await depot.ListerAsync(fil, Ns, "1ef-0004", null, ct);
        var limite = await depot.ListerAsync(fil, Ns, "1ef-0004", 2, ct);

        Assert.Equal(["1ef-0009", "1ef-0004", "1ef-0003", "1ef-0002", "1ef-0001"], tous.Select(p => p.CheckpointId));
        Assert.Equal(["1ef-0004", "1ef-0003", "1ef-0002", "1ef-0001"], racine.Select(p => p.CheckpointId));
        Assert.Equal(["1ef-0003", "1ef-0002", "1ef-0001"], avant.Select(p => p.CheckpointId));
        Assert.Equal(["1ef-0003", "1ef-0002"], limite.Select(p => p.CheckpointId));
        Assert.Equal([4], racine[0].Ecritures.Single().Valeur);
        Assert.Empty(racine[1].Ecritures);
    }

    [Fact]
    public async Task Ecriture_speciale_idx_negatif_remplace()
    {
        var ct = TestContext.Current.CancellationToken;
        var depot = await Preparer();
        var fil = UnFil();
        await depot.EcrireAsync(UnPoint(fil, "1ef-0001"), ct);
        await depot.EcrireEcrituresAsync(fil, Ns, "1ef-0001", "t", "p", [UneEcriture("t", -1, [1], "ancien")], ct);

        await depot.EcrireEcrituresAsync(fil, Ns, "1ef-0001", "t", "p", [UneEcriture("t", -1, [2], "nouveau")], ct);

        var ecriture = (await depot.LireAsync(fil, Ns, "1ef-0001", ct))?.Ecritures.Single();
        Assert.Equal([2], ecriture?.Valeur);
        Assert.Equal("nouveau", ecriture?.Canal);
    }

    [Fact]
    public async Task Ecriture_normale_existante_ignoree()
    {
        var ct = TestContext.Current.CancellationToken;
        var depot = await Preparer();
        var fil = UnFil();
        await depot.EcrireAsync(UnPoint(fil, "1ef-0001"), ct);
        await depot.EcrireEcrituresAsync(fil, Ns, "1ef-0001", "t", "p", [UneEcriture("t", 0, [1], "premier")], ct);

        await depot.EcrireEcrituresAsync(fil, Ns, "1ef-0001", "t", "p", [UneEcriture("t", 0, [2], "second"), UneEcriture("t", 1, [3])], ct);

        var ecritures = (await depot.LireAsync(fil, Ns, "1ef-0001", ct))!.Ecritures;
        Assert.Equal([([1], "premier"), ([3], "canal")], ecritures.Select(e => (e.Valeur, e.Canal)));
    }

    [Fact]
    public async Task Suppression_du_fil_retire_points_et_ecritures()
    {
        var ct = TestContext.Current.CancellationToken;
        var depot = await Preparer();
        var fil = UnFil();
        var autre = UnFil();
        foreach (var f in new[] { fil, autre })
        {
            await depot.EcrireAsync(UnPoint(f, "1ef-0001"), ct);
            await depot.EcrireEcrituresAsync(f, Ns, "1ef-0001", "t", "p", [UneEcriture("t", 0, [1])], ct);
        }

        await depot.SupprimerFilAsync(fil, ct);

        Assert.Empty(await depot.ListerAsync(fil, null, null, null, ct));
        Assert.Equal(0, await Compter("ecriture", fil));
        Assert.Single((await depot.LireAsync(autre, Ns, null, ct))!.Ecritures);
    }

    [Fact]
    public async Task Compte_points_reprise_ne_lit_pas_les_dossiers()
    {
        var ct = TestContext.Current.CancellationToken;
        await Preparer();
        await MigrationsDossiers.AppliquerAsync(
            new ConnexionsDossiers(Hote, Port, "_test", Env("PG_MIGRATEUR_PASSWORD"), Env("PG_DOSSIERS_PASSWORD")), TimeSpan.FromSeconds(30), ct);
        var chaine = new NpgsqlConnectionStringBuilder
        {
            Host = Hote,
            Port = Port,
            Database = "dossiers_test",
            Username = "points_reprise",
            Password = Env("PG_POINTS_REPRISE_PASSWORD"),
        }.ConnectionString;

        foreach (var table in new[] { "public.contrat", "public.souscripteur", "public.vue_contrat_minimisee" })
        {
            var erreur = await Assert.ThrowsAsync<PostgresException>(() => Scalaire(chaine, $"SELECT count(*) FROM {table}"));
            Assert.Equal(PostgresErrorCodes.InsufficientPrivilege, erreur.SqlState);
        }
        await Assert.ThrowsAsync<PostgresException>(() => Scalaire(chaine, "CREATE TABLE points_reprise.intrus (x int)"));
        Assert.NotNull(await Scalaire(chaine, "SELECT count(*) FROM points_reprise.checkpoint"));
    }

    private static async Task<long> Compter(string table, string fil)
    {
        await using var cx = new NpgsqlConnection(Connexions().PointsDeReprise);
        await cx.OpenAsync(TestContext.Current.CancellationToken);
        await using var cmd = new NpgsqlCommand($"SELECT count(*) FROM points_reprise.{table} WHERE thread_id = @t", cx);
        cmd.Parameters.AddWithValue("t", fil);
        return (long)(await cmd.ExecuteScalarAsync(TestContext.Current.CancellationToken))!;
    }

    private static async Task<object?> Scalaire(string chaine, string sql)
    {
        await using var cx = new NpgsqlConnection(chaine);
        await cx.OpenAsync(TestContext.Current.CancellationToken);
        await using var cmd = new NpgsqlCommand(sql, cx);
        return await cmd.ExecuteScalarAsync(TestContext.Current.CancellationToken);
    }
}
