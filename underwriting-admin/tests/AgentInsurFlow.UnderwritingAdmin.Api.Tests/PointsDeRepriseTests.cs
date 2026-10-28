using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using OpenTelemetry.Trace;

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>TI : API des points de reprise du cluster (D105), jetons réels, dépôt simulé en mémoire.</summary>
public sealed class PointsDeRepriseTests : IDisposable
{
    private const string Fil = "AIF-2026-000001";
    private const string Secret = "CORPS-SECRET";

    private sealed class DepotEnMemoire : IDepotPointsDeReprise
    {
        public List<PointDeReprise> Points { get; } = [];
        public List<EcritureEnAttente> Ecritures { get; } = [];

        public Task<PointDeReprise?> LireAsync(string threadId, string ns, string? checkpointId, CancellationToken ct)
        {
            var candidats = Points.Where(p => p.ThreadId == threadId && p.Ns == ns && (checkpointId is null || p.CheckpointId == checkpointId));
            var point = candidats.OrderByDescending(p => p.CheckpointId).FirstOrDefault();
            return Task.FromResult(point is null ? null : point with { Ecritures = [.. Ecritures] });
        }

        public Task<IReadOnlyList<PointDeReprise>> ListerAsync(string threadId, string? ns, string? avant, int? limite, CancellationToken ct) =>
            Task.FromResult<IReadOnlyList<PointDeReprise>>([.. Points.Where(p => p.ThreadId == threadId && (ns is null || p.Ns == ns))
                .Where(p => avant is null || string.CompareOrdinal(p.CheckpointId, avant) < 0)
                .OrderByDescending(p => p.CheckpointId).Take(limite ?? int.MaxValue)]);

        public Task EcrireAsync(PointDeReprise point, CancellationToken ct)
        {
            Points.RemoveAll(p => p.ThreadId == point.ThreadId && p.Ns == point.Ns && p.CheckpointId == point.CheckpointId);
            Points.Add(point);
            return Task.CompletedTask;
        }

        public Task EcrireEcrituresAsync(string threadId, string ns, string checkpointId, string taskId, string taskPath,
            IReadOnlyList<EcritureEnAttente> ecritures, CancellationToken ct)
        {
            Ecritures.AddRange(ecritures);
            return Task.CompletedTask;
        }

        public Task SupprimerFilAsync(string threadId, CancellationToken ct)
        {
            Points.RemoveAll(p => p.ThreadId == threadId);
            Ecritures.Clear();
            return Task.CompletedTask;
        }
    }

    private readonly DepotEnMemoire _depot = new();
    private readonly List<Activity> _activites = []; // alimentée par l'exportateur sur un autre thread : lire par ToArray()
    private readonly WebApplicationFactory<Program> _usine;

    public PointsDeRepriseTests() => _usine = JetonsDeTest.Usine(b => b.ConfigureTestServices(s =>
    {
        s.RemoveAll<IDepotPointsDeReprise>();
        s.AddSingleton<IDepotPointsDeReprise>(_depot);
        s.ConfigureOpenTelemetryTracerProvider(t => t.AddInMemoryExporter(_activites));
    }));

    public void Dispose() => _usine.Dispose();

    private async Task<(HttpStatusCode Statut, JsonElement Corps)> Appeler(HttpMethod methode, string chemin, string? jeton, object? corps = null)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(methode, chemin);
        if (corps is not null) requete.Content = JsonContent.Create(corps);
        if (jeton is not null) requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", jeton);
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var texte = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        return (reponse.StatusCode, texte.Length == 0 ? default : JsonDocument.Parse(texte).RootElement.Clone());
    }

    private static string Cluster() => JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, "oid-cluster", "PointsDeReprise");

    private static string B64(string texte) => Convert.ToBase64String(Encoding.UTF8.GetBytes(texte));

    private static object Point(string id, string contenu = "cp") => new
    {
        ns = "",
        checkpoint_id = id,
        parent_id = (string?)null,
        type = "msgpack",
        checkpoint = B64(contenu),
        type_metadata = "json",
        metadata = B64("{}"),
    };

    // Le span serveur se termine après la réponse (#160) : attente bornée, jamais un simple ForceFlush.
    // Seuls les spans de cette route : ActivitySource est global, les autres classes de tests y écrivent en parallèle.
    private async Task<Activity[]> SpansAttendus()
    {
        var limite = DateTime.UtcNow.AddSeconds(5);
        while (true)
        {
            _usine.Services.GetRequiredService<TracerProvider>().ForceFlush();
            var spans = _activites.ToArray().Where(a => a.Kind == ActivityKind.Server
                && a.GetTagItem("http.route") is string route && route.Contains("points-de-reprise", StringComparison.Ordinal)).ToArray();
            if (spans.Length > 0 || DateTime.UtcNow >= limite) return spans;
            await Task.Delay(50, TestContext.Current.CancellationToken);
        }
    }

    [Fact]
    public async Task Aller_retour_point_et_ecritures()
    {
        var octets = Convert.ToBase64String([1, 2, 3, 255]);
        var (ecrit, _) = await Appeler(HttpMethod.Put, $"/api/points-de-reprise/{Fil}", Cluster(), new
        {
            ns = "",
            checkpoint_id = "cp-1",
            parent_id = (string?)null,
            type = "msgpack",
            checkpoint = octets,
            type_metadata = "json",
            metadata = octets,
        });
        var (ecritures, _) = await Appeler(HttpMethod.Put, $"/api/points-de-reprise/{Fil}/ecritures", Cluster(), new
        {
            ns = "",
            checkpoint_id = "cp-1",
            task_id = "t1",
            task_path = "p",
            ecritures = new[] { new { idx = 0, canal = "messages", type = "msgpack", valeur = octets } },
        });
        var (lu, corps) = await Appeler(HttpMethod.Get, $"/api/points-de-reprise/{Fil}?ns=&id=cp-1", Cluster());

        Assert.Equal(HttpStatusCode.NoContent, ecrit);
        Assert.Equal(HttpStatusCode.NoContent, ecritures);
        Assert.Equal(HttpStatusCode.OK, lu);
        Assert.Equal("cp-1", corps.GetProperty("checkpoint_id").GetString());
        Assert.Equal(octets, corps.GetProperty("checkpoint").GetString());
        Assert.Equal("json", corps.GetProperty("type_metadata").GetString());
        var e = Assert.Single(corps.GetProperty("ecritures").EnumerateArray());
        Assert.Equal("t1", e.GetProperty("task_id").GetString());
        Assert.Equal("messages", e.GetProperty("canal").GetString());
        Assert.Equal("p", e.GetProperty("task_path").GetString());
        Assert.Equal(octets, e.GetProperty("valeur").GetString());
    }

    [Fact]
    public async Task Lecture_du_dernier_point_sans_id()
    {
        await Appeler(HttpMethod.Put, $"/api/points-de-reprise/{Fil}", Cluster(), Point("cp-1"));
        await Appeler(HttpMethod.Put, $"/api/points-de-reprise/{Fil}", Cluster(), Point("cp-2"));

        var (statut, corps) = await Appeler(HttpMethod.Get, $"/api/points-de-reprise/{Fil}", Cluster());
        var (_, liste) = await Appeler(HttpMethod.Get, $"/api/points-de-reprise/{Fil}/liste?limite=5", Cluster());

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal("cp-2", corps.GetProperty("checkpoint_id").GetString());
        Assert.Equal(["cp-2", "cp-1"], liste.GetProperty("points").EnumerateArray().Select(p => p.GetProperty("checkpoint_id").GetString()));
    }

    [Fact]
    public async Task Point_absent_404_avec_code()
    {
        var (statut, corps) = await Appeler(HttpMethod.Get, $"/api/points-de-reprise/{Fil}", Cluster());

        Assert.Equal(HttpStatusCode.NotFound, statut);
        Assert.Equal("POINT_DE_REPRISE_INTROUVABLE", corps.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Suppression_du_fil()
    {
        await Appeler(HttpMethod.Put, $"/api/points-de-reprise/{Fil}", Cluster(), Point("cp-1"));

        var (statut, _) = await Appeler(HttpMethod.Delete, $"/api/points-de-reprise/{Fil}", Cluster());
        var (apres, _) = await Appeler(HttpMethod.Get, $"/api/points-de-reprise/{Fil}", Cluster());

        Assert.Equal(HttpStatusCode.NoContent, statut);
        Assert.Equal(HttpStatusCode.NotFound, apres);
    }

    [Fact]
    public async Task Corps_incomplet_400_avec_code()
    {
        var (statut, corps) = await Appeler(HttpMethod.Put, $"/api/points-de-reprise/{Fil}", Cluster(), new { ns = "" });

        Assert.Equal(HttpStatusCode.BadRequest, statut);
        Assert.Equal("CORPS_INVALIDE", corps.GetProperty("code").GetString());
    }

    [Theory]
    [InlineData("Gestionnaire")]
    [InlineData("Telemetrie")]
    public async Task Points_de_reprise_refuses_sans_role(string role)
    {
        var jeton = JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, "oid-x", role);
        var vide = new { ns = "", checkpoint_id = "c", type = "t", checkpoint = "", type_metadata = "t", metadata = "", task_id = "t", ecritures = Array.Empty<object>() };
        (HttpMethod, string)[] routes =
        [
            (HttpMethod.Get, $"/api/points-de-reprise/{Fil}"),
            (HttpMethod.Get, $"/api/points-de-reprise/{Fil}/liste"),
            (HttpMethod.Put, $"/api/points-de-reprise/{Fil}"),
            (HttpMethod.Put, $"/api/points-de-reprise/{Fil}/ecritures"),
            (HttpMethod.Delete, $"/api/points-de-reprise/{Fil}"),
        ];
        foreach (var (methode, chemin) in routes)
        {
            var (statut, corps) = await Appeler(methode, chemin, jeton, methode == HttpMethod.Put ? vide : null);
            Assert.Equal(HttpStatusCode.Forbidden, statut);
            Assert.Equal("ACCES_REFUSE", corps.GetProperty("code").GetString());
        }
        Assert.Empty(_depot.Points);
    }

    [Fact]
    public async Task Sans_jeton_401()
    {
        var (statut, corps) = await Appeler(HttpMethod.Get, $"/api/points-de-reprise/{Fil}", null);

        Assert.Equal(HttpStatusCode.Unauthorized, statut);
        Assert.Equal("NON_AUTHENTIFIE", corps.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Span_points_de_reprise_sans_numero()
    {
        await Appeler(HttpMethod.Get, $"/api/points-de-reprise/{Fil}?ns=&id=cp-1", Cluster());
        var spans = await SpansAttendus();

        var serveur = Assert.Single(spans);
        Assert.Contains("/api/points-de-reprise/{thread_id}", serveur.DisplayName, StringComparison.Ordinal);
        var textes = spans.SelectMany(a => a.TagObjects.Select(t => t.Value?.ToString() ?? "").Append(a.DisplayName));
        Assert.DoesNotContain(textes, t => t.Contains("AIF-", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Corps_jamais_dans_un_span()
    {
        await Appeler(HttpMethod.Put, $"/api/points-de-reprise/{Fil}", Cluster(), Point("cp-1", Secret));
        var spans = await SpansAttendus();

        Assert.NotEmpty(spans);
        var contenu = string.Join('|', spans.SelectMany(a => a.TagObjects.Select(t => $"{t.Key}={t.Value}").Append(a.DisplayName)));
        Assert.DoesNotContain(Secret, contenu, StringComparison.Ordinal);
        Assert.DoesNotContain(B64(Secret), contenu, StringComparison.Ordinal);
    }
}
