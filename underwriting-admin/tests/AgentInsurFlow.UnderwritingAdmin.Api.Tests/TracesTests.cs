using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Application;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using OpenTelemetry;
using OpenTelemetry.Proto.Collector.Trace.V1;
using OpenTelemetry.Proto.Common.V1;
using OpenTelemetry.Proto.Resource.V1;
using OpenTelemetry.Trace;
using Google.Protobuf;
using OtlpSpan = OpenTelemetry.Proto.Trace.V1.Span;

namespace AgentInsurFlow.UnderwritingAdmin.Api.Tests;

/// <summary>TI : <c>POST /v1/traces</c> (règle S3-21) et <c>GET /api/traces/{trace_id}</c>, jetons réels, dépôt en mémoire.</summary>
public sealed class TracesTests : IDisposable
{
    private const string TraceId = "0af7651916cd43dd8448eb211c80319c";

    private sealed class DepotEnMemoire : IDepotTraces
    {
        private readonly Dictionary<(string, string), Domain.Span> _spans = [];

        public Task<int> Inserer(IReadOnlyList<Domain.Span> spans, CancellationToken ct) =>
            Task.FromResult(spans.Count(s => _spans.TryAdd((s.TraceId, s.SpanId), s)));

        public Task<IReadOnlyList<Domain.Span>> Lire(string traceId, CancellationToken ct) =>
            Task.FromResult<IReadOnlyList<Domain.Span>>(
                _spans.Values.Where(s => s.TraceId == traceId).OrderBy(s => s.StartTimeUnixNano).ToList());
    }

    /// <summary>TestServer n'a pas d'adresse source : l'en-tête <c>X-Test-Ip</c> en fixe une, comme le ferait Kestrel.</summary>
    private sealed class SourceDeTest : IStartupFilter
    {
        public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> suivant) => app =>
        {
            app.Use((ctx, next) =>
            {
                if (ctx.Request.Headers.TryGetValue("X-Test-Ip", out var ip))
                {
                    ctx.Connection.RemoteIpAddress = IPAddress.Parse(ip.ToString());
                }
                return next(ctx);
            });
            suivant(app);
        };
    }

    private readonly DepotEnMemoire _depot = new();
    private readonly List<Activity> _activites = [];
    private readonly WebApplicationFactory<Program> _usine;

    public TracesTests() => _usine = Usine(null);

    private WebApplicationFactory<Program> Usine(string? sources) => JetonsDeTest.Usine(b =>
    {
        if (sources is not null)
        {
            b.UseSetting("Otlp:SourcesSansJeton", sources);
        }
        b.ConfigureTestServices(s =>
        {
            s.RemoveAll<IDepotTraces>();
            s.AddSingleton<IDepotTraces>(_depot);
            s.AddSingleton<IStartupFilter, SourceDeTest>();
            s.ConfigureOpenTelemetryTracerProvider(t => t.AddInMemoryExporter(_activites));
        });
    });

    public void Dispose() => _usine.Dispose();

    private static ByteArrayContent Otlp(string spanId = "b7ad6b7169203331", long debut = 1_000, string? service = "rag")
    {
        var ressource = new Resource();
        if (service is not null)
        {
            ressource.Attributes.Add(new KeyValue { Key = "service.name", Value = new AnyValue { StringValue = service } });
        }
        var span = new OtlpSpan
        {
            TraceId = ByteString.CopyFrom(Convert.FromHexString(TraceId)),
            SpanId = ByteString.CopyFrom(Convert.FromHexString(spanId)),
            Name = "rag.recherche",
            StartTimeUnixNano = (ulong)debut,
            EndTimeUnixNano = (ulong)debut + 1_000_000,
        };
        var requete = new ExportTraceServiceRequest { ResourceSpans = { new OpenTelemetry.Proto.Trace.V1.ResourceSpans { Resource = ressource, ScopeSpans = { new OpenTelemetry.Proto.Trace.V1.ScopeSpans { Spans = { span } } } } } };
        return Contenu(requete.ToByteArray(), "application/x-protobuf");
    }

    private static ByteArrayContent Contenu(byte[] octets, string type)
    {
        var contenu = new ByteArrayContent(octets);
        contenu.Headers.ContentType = new MediaTypeHeaderValue(type);
        return contenu;
    }

    private async Task<HttpResponseMessage> Poster(HttpContent contenu, string? ip = null, bool via = false, string? jeton = null,
        WebApplicationFactory<Program>? usine = null)
    {
        using var client = (usine ?? _usine).CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Post, "/v1/traces") { Content = contenu };
        if (ip is not null)
        {
            requete.Headers.Add("X-Test-Ip", ip);
        }
        if (via)
        {
            requete.Headers.Add("X-Forwarded-For", "203.0.113.7");
        }
        if (jeton is not null)
        {
            requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", jeton);
        }
        return await client.SendAsync(requete, TestContext.Current.CancellationToken);
    }

    private async Task<(HttpStatusCode Statut, JsonElement Corps)> Lire(string chemin, params string[] roles)
    {
        using var client = _usine.CreateClient();
        using var requete = new HttpRequestMessage(HttpMethod.Get, chemin);
        if (roles.Length > 0)
        {
            requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, "oid-1", roles));
        }
        using var reponse = await client.SendAsync(requete, TestContext.Current.CancellationToken);
        var texte = await reponse.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);
        return (reponse.StatusCode, texte.Length == 0 ? default : JsonDocument.Parse(texte).RootElement.Clone());
    }

    private static string JetonTelemetrie(params string[] roles) => JetonsDeTest.Jeton(JetonsDeTest.AudienceParDefaut, "oid-ci", roles);

    [Theory]
    [InlineData("127.0.0.1")]
    [InlineData("::1")]
    [InlineData("::ffff:127.0.0.1")]
    public async Task V1Traces_loopback_sans_jeton_accepte(string ip)
    {
        using var reponse = await Poster(Otlp(), ip);

        Assert.Equal(HttpStatusCode.OK, reponse.StatusCode);
        Assert.Equal("application/x-protobuf", reponse.Content.Headers.ContentType?.MediaType);
        Assert.Empty(await reponse.Content.ReadAsByteArrayAsync(TestContext.Current.CancellationToken)); // ExportTraceServiceResponse vide
        var enregistres = await _depot.Lire(TraceId, TestContext.Current.CancellationToken);
        Assert.Equal("rag", Assert.Single(enregistres).ServiceName);
    }

    [Fact]
    public void Cidr_invalide_nomme_la_cle_et_la_valeur()
    {
        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["Otlp:SourcesSansJeton"] = "127.0.0.1/32, pas-un-cidr" })
            .Build();

        var erreur = Assert.Throws<InvalidOperationException>(() => new SourcesSansJetonHandler(config));
        Assert.Contains("Otlp:SourcesSansJeton", erreur.Message, StringComparison.Ordinal);
        Assert.Contains("pas-un-cidr", erreur.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task V1Traces_via_gateway_sans_jeton_401()
    {
        using var reponse = await Poster(Otlp(), "127.0.0.1", via: true);

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        Assert.Empty(await _depot.Lire(TraceId, TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task V1Traces_source_hors_liste_sans_jeton_401()
    {
        using var reponse = await Poster(Otlp(), "10.1.2.3");
        using var sansAdresse = await Poster(Otlp());

        Assert.Equal(HttpStatusCode.Unauthorized, reponse.StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, sansAdresse.StatusCode);
    }

    [Fact]
    public async Task V1Traces_reseau_ajoute_a_la_liste_accepte_sans_jeton()
    {
        using var usine = Usine("127.0.0.1/32, 172.30.0.0/16");

        using var dedans = await Poster(Otlp(), "172.30.4.5", usine: usine);
        using var dehors = await Poster(Otlp(), "172.31.0.1", usine: usine);

        Assert.Equal(HttpStatusCode.OK, dedans.StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, dehors.StatusCode);
    }

    [Fact]
    public async Task V1Traces_avec_le_role_Telemetrie_accepte_et_sans_le_role_403()
    {
        using var accepte = await Poster(Otlp(), "10.1.2.3", via: true, jeton: JetonTelemetrie("Telemetrie"));
        using var refuse = await Poster(Otlp("c7ad6b7169203331"), "10.1.2.3", via: true, jeton: JetonTelemetrie("Gestionnaire"));

        Assert.Equal(HttpStatusCode.OK, accepte.StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, refuse.StatusCode);
    }

    [Fact]
    public async Task V1Traces_json_415()
    {
        using var reponse = await Poster(Contenu("{}"u8.ToArray(), "application/json"), "127.0.0.1");

        Assert.Equal(HttpStatusCode.UnsupportedMediaType, reponse.StatusCode);
    }

    [Fact]
    public async Task V1Traces_corps_illisible_400()
    {
        using var reponse = await Poster(Contenu([0x0a, 0xff, 0x01], "application/x-protobuf"), "127.0.0.1");

        Assert.Equal(HttpStatusCode.BadRequest, reponse.StatusCode);
    }

    [Fact]
    public async Task Trace_complete_relue_dans_l_ordre()
    {
        // Envoyée dans le désordre, par deux requêtes ; rejouer la première n'ajoute rien
        (await Poster(Otlp("0000000000000002", 2_000), "127.0.0.1")).Dispose();
        (await Poster(Otlp("0000000000000001", 1_000), "127.0.0.1")).Dispose();
        (await Poster(Otlp("0000000000000001", 1_000), "127.0.0.1")).Dispose();

        var (statut, corps) = await Lire($"/api/traces/{TraceId.ToUpperInvariant()}", "Gestionnaire");

        Assert.Equal(HttpStatusCode.OK, statut);
        Assert.Equal(["0000000000000001", "0000000000000002"], corps.EnumerateArray().Select(s => s.GetProperty("span_id").GetString()));
        Assert.Equal(1.0, corps[0].GetProperty("duree_ms").GetDouble());
        Assert.Equal(JsonValueKind.Object, corps[0].GetProperty("attributes").ValueKind);
    }

    [Fact]
    public async Task Trace_inconnue_404_identifiant_invalide_400()
    {
        var (inconnue, probleme) = await Lire("/api/traces/" + new string('a', 32), "Gestionnaire");
        var (invalide, autre) = await Lire("/api/traces/pas-un-identifiant", "Gestionnaire");

        Assert.Equal(HttpStatusCode.NotFound, inconnue);
        Assert.Equal("TRACE_INTROUVABLE", probleme.GetProperty("code").GetString());
        Assert.Equal(HttpStatusCode.BadRequest, invalide);
        Assert.Equal("TRACE_ID_INVALIDE", autre.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Trace_sans_jeton_401_et_sans_role_Gestionnaire_403()
    {
        Assert.Equal(HttpStatusCode.Unauthorized, (await Lire($"/api/traces/{TraceId}")).Statut);
        Assert.Equal(HttpStatusCode.Forbidden, (await Lire($"/api/traces/{TraceId}", "Telemetrie")).Statut);
    }

    [Fact]
    public async Task V1Traces_ne_se_trace_pas_lui_meme()
    {
        (await Poster(Otlp(), "127.0.0.1")).Dispose();
        await Lire($"/api/traces/{TraceId}", "Gestionnaire"); // témoin : cette route-là est bien tracée

        for (var i = 0; i < 40 && !_activites.Any(a => Chemin(a).StartsWith("/api/traces", StringComparison.Ordinal)); i++)
        {
            await Task.Delay(50, TestContext.Current.CancellationToken);
        }
        Assert.Contains(_activites, a => Chemin(a).StartsWith("/api/traces", StringComparison.Ordinal));
        Assert.DoesNotContain(_activites, a => Chemin(a).StartsWith("/v1/traces", StringComparison.Ordinal));
    }

    private static string Chemin(Activity a) => a.GetTagItem("url.path")?.ToString() ?? "";

    [Fact]
    public async Task OpenApi_declare_les_deux_routes_et_leurs_erreurs()
    {
        using var client = _usine.CreateClient();
        var doc = JsonDocument.Parse(await client.GetStringAsync(new Uri("/openapi/v1.json", UriKind.Relative), TestContext.Current.CancellationToken)).RootElement;
        var chemins = doc.GetProperty("paths");

        var lecture = chemins.GetProperty("/api/traces/{trace_id}").GetProperty("get").GetProperty("responses");
        var reception = chemins.GetProperty("/v1/traces").GetProperty("post").GetProperty("responses");

        Assert.Equal(["200", "400", "401", "403", "404"], lecture.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal));
        Assert.Equal(["200", "400", "401", "403", "415"], reception.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal));
    }
}
