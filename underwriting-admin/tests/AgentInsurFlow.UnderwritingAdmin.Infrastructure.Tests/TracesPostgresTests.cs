using AgentInsurFlow.UnderwritingAdmin.Domain;
using AgentInsurFlow.UnderwritingAdmin.Infrastructure.Traces;
using Npgsql;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests;

/// <summary>TI : base <c>traces_test</c> du PostgreSQL du compose (<c>docker compose up -d postgres</c>, variables PG_* du .env).</summary>
public sealed class TracesPostgresTests
{
    private static string Env(string nom) => Environment.GetEnvironmentVariable(nom)
        ?? throw new InvalidOperationException($"{nom} manquant : lancer `docker compose up -d postgres` et exporter les PG_* du .env");

    private static ConnexionsTraces Connexions() => new(
        Environment.GetEnvironmentVariable("PG_HOST") ?? "localhost",
        int.Parse(Environment.GetEnvironmentVariable("PG_PORT") ?? "5432", System.Globalization.CultureInfo.InvariantCulture),
        "_test", Env("PG_MIGRATEUR_PASSWORD"), Env("PG_TRACES_WRITER_PASSWORD"), Env("PG_TRACES_READER_PASSWORD"));

    private static Span UnSpan(string traceId, string spanId, long debut, string? parent = null) => new(
        traceId, spanId, parent, "", "rag.recherche", 2, debut, debut + 250_000_000, 0, "", "rag",
        """{"service.name":"rag"}""", """{"rag.statut":"ok"}""", "portee", "1.0", "[]", "[]", DateTimeOffset.UtcNow);

    private static async Task<object?> Scalaire(string chaine, string sql)
    {
        await using var cx = new NpgsqlConnection(chaine);
        await cx.OpenAsync(TestContext.Current.CancellationToken);
        await using var cmd = new NpgsqlCommand(sql, cx);
        return await cmd.ExecuteScalarAsync(TestContext.Current.CancellationToken);
    }

    [Fact]
    public async Task Trace_complete_relue_dans_l_ordre_et_rejeu_idempotent()
    {
        var ct = TestContext.Current.CancellationToken;
        await MigrationsTraces.AppliquerAsync(Connexions(), TimeSpan.FromSeconds(30), ct);
        var depot = new DepotTracesEf(Connexions());
        var trace = Guid.NewGuid().ToString("N");
        // Insérés volontairement dans le désordre
        Span[] spans = [UnSpan(trace, "0000000000000003", 3_000), UnSpan(trace, "0000000000000001", 1_000), UnSpan(trace, "0000000000000002", 2_000, "0000000000000001")];

        var premier = await depot.Inserer(spans, ct);
        var rejeu = await depot.Inserer(spans, ct);
        var relus = await depot.Lire(trace, ct);

        Assert.Equal(3, premier);
        Assert.Equal(0, rejeu);
        Assert.Equal(["0000000000000001", "0000000000000002", "0000000000000003"], relus.Select(s => s.SpanId));
        Assert.Equal("0000000000000001", relus[1].ParentSpanId);
        Assert.Equal(250.0, relus[0].DureeMs);
        Assert.Equal("""{"rag.statut": "ok"}""", relus[0].Attributes); // jsonb normalise l'espacement
        Assert.Empty(await depot.Lire(Guid.NewGuid().ToString("N"), ct));
    }

    [Fact]
    public async Task Insertion_par_lots_au_dela_d_un_lot_puis_rejeu_idempotent()
    {
        var ct = TestContext.Current.CancellationToken;
        await MigrationsTraces.AppliquerAsync(Connexions(), TimeSpan.FromSeconds(30), ct);
        var depot = new DepotTracesEf(Connexions());
        var trace = Guid.NewGuid().ToString("N");
        var spans = Enumerable.Range(1, DepotTracesEf.SpansParLot + 1)
            .Select(i => UnSpan(trace, i.ToString("x16", System.Globalization.CultureInfo.InvariantCulture), i)).ToArray();

        Assert.Equal(spans.Length, await depot.Inserer(spans, ct)); // deux lots
        Assert.Equal(0, await depot.Inserer(spans, ct));
        Assert.Equal(spans.Length, (await depot.Lire(trace, ct)).Count);
    }

    [Fact]
    public void Insertion_par_lots_une_requete_parametree_par_lot()
    {
        var trace = Guid.NewGuid().ToString("N");
        var (sql, parametres) = DepotTracesEf.InsertionParLot([UnSpan(trace, "0000000000000001", 1), UnSpan(trace, "0000000000000002", 2, "0000000000000001")]);

        Assert.Equal(36, parametres.Length);
        Assert.Equal(1, sql.Split("INSERT INTO span").Length - 1);
        Assert.DoesNotContain(trace, sql, StringComparison.Ordinal); // aucune valeur dans le texte SQL
        Assert.Equal(DBNull.Value, parametres[2].Value); // parent absent du premier span
    }

    [Fact]
    public async Task Droits_writer_insere_seulement_reader_lit_seulement()
    {
        await MigrationsTraces.AppliquerAsync(Connexions(), TimeSpan.FromSeconds(30), TestContext.Current.CancellationToken);

        await Assert.ThrowsAsync<PostgresException>(() => Scalaire(Connexions().Writer, "SELECT count(*) FROM span"));
        await Assert.ThrowsAsync<PostgresException>(() => Scalaire(Connexions().Reader, "DELETE FROM span"));
        await Assert.ThrowsAsync<PostgresException>(() => Scalaire(Connexions().Reader,
            "INSERT INTO span (trace_id, span_id, name, kind, start_time_unix_nano, end_time_unix_nano, status_code, service_name, recu_le) " +
            "VALUES ('a', 'b', 'n', 0, 0, 0, 0, 's', now())"));
        Assert.NotNull(await Scalaire(Connexions().Reader, "SELECT count(*) FROM span"));
    }
}
